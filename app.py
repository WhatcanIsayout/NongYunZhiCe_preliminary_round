import os
import json
import re
import pandas as pd
import dashscope
from werkzeug.utils import secure_filename
import time
from http import HTTPStatus
from flask import Flask, render_template, request, jsonify, session
from datetime import timedelta




app = Flask(__name__)

app.secret_key = 'nongyunzhice-ultimate-final-version-key'
app.permanent_session_lifetime = timedelta(minutes=30)

# 配置上传文件夹
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 从环境变量安全获取API Key
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    raise ValueError("错误：未找到 DASHSCOPE_API_KEY 环境变量。请配置后重启。")
dashscope.api_key = api_key


try:
    df_variety = pd.read_excel('database/1. 基础品种信息表.xlsx')
    df_disease = pd.read_excel('database/2. 病害特征表.xlsx')
    df_nutrient = pd.read_excel('database/3. 营养缺乏症状表.xlsx')
    print("所有Excel知识库加载成功！")
except FileNotFoundError as e:
    print(f"警告：数据库文件未找到 - {e}。知识库相关功能将受限。")
    df_variety, df_disease, df_nutrient = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()



def call_text_model(prompt, model_name='qwen-plus', temperature=0.7):
    """统一调用文本生成模型"""
    try:
        response = dashscope.Generation.call(model=model_name, prompt=prompt, temperature=temperature, result_format='message')
        if response.status_code == HTTPStatus.OK:
            return response.output.choices[0].message.content
        else:
            print(f"API调用失败: Code: {response.code}, Message: {response.message}")
            return f"抱歉，AI模型调用失败 (模型: {model_name})。错误信息: {response.message}"
    except Exception as e:
        print(f"网络或API异常: {e}")
        return f"抱歉，与AI大脑连接时发生网络或API异常: {e}"

def call_image_model(prompt, model_name='wanx-v1'):
    """专门调用通义万相文生图模型"""
    if not prompt:
        return None
    try:
        response = dashscope.ImageSynthesis.call(model=model_name, prompt=prompt, n=1, size='1024*1024')
        if response.status_code == HTTPStatus.OK:
            return response.output.results[0].url
        else:
            return None
    except Exception as e:
        print(f"调用文生图模型时发生异常: {e}")
        return None

def extract_json_from_text(text):
    """从文本中提取最后一个 ```json ... ``` 代码块或纯JSON字符串并解析"""
    if not isinstance(text, str):
        return None
    # 优先匹配 markdown格式的 JSON 代码块
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.MULTILINE)
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            print(f"JSON块解析失败: {json_str}")
            return None
    # 如果没匹配到，尝试直接解析整个文本
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # print(f"直接解析文本为JSON失败: {text}")
        return None


def call_vl_model(prompt, local_image_path):
    """
    专门调用通义千问VL多模态模型 (V4 - 修正返回格式)
    """
    if not local_image_path or not os.path.exists(local_image_path):
        return "错误：需要图片但未收到有效的图片文件路径。"
    
    image_url_for_sdk = f"file://{os.path.abspath(local_image_path)}"
    
    messages = [{'role': 'user', 'content': [
        {'image': image_url_for_sdk},
        {'text': prompt}
    ]}]
    
    try:
        response = dashscope.MultiModalConversation.call(model='qwen-vl-max', messages=messages)
        if response.status_code == HTTPStatus.OK:
            
            content_list = response.output.choices[0].message.content
            text_content = ""
            for item in content_list:
                if 'text' in item:
                    text_content += item['text']
            return text_content # 确保返回的是一个纯净的字符串
        else:
            return f"调用多模态模型失败: Code: {response.code}, Message: {response.message}"
    except Exception as e:
        return f"与多模态AI连接时发生严重错误: {e}"

def run_workflow_A(context):
    """Part A: 种植决策 (V5 - 标准化参数与记忆清空逻辑)"""
    user_input = context.get('user_input', '')

    
    env_keys_to_clear = ['region', 'suntime', 'humidity', 'soilpH'] # 使用旧的参数名列表进行清理
    for key in env_keys_to_clear:
        context.pop(key, None) # 从context中安全地移除

    
    param_extraction_prompt = f"""
System: 你是一个精准的信息提取助手。你的任务是从用户的自然语言问题中，严格按照以下要求提取环境参数，并以纯JSON格式返回。

**提取规则:**
- `region` (string): 用户提到的地理位置，如省份、城市。
- `suntime` (number): 日照时长，单位为小时。
- `humidity` (number): 湿度百分比，请只提取数值。
- `soilpH` (number): 土壤的pH值。

如果某个信息在用户问题中没有提及，请在JSON中将对应的值设为 `null`。

**用户问题:** "{user_input}"

**请输出严格的JSON对象:**
"""
    params_str = call_text_model(param_extraction_prompt, 'qwen-turbo')
    extracted_params = extract_json_from_text(params_str)
    
    
    if extracted_params:
        # 只更新那些被成功提取出来的值（非null）
        valid_params = {k: v for k, v in extracted_params.items() if v is not None}
        context.update(valid_params)
        print(f"记忆更新 [模式A-环境]: {valid_params}")

    
    prompt1 = f"""
System: 你是一位顶级的农业种植顾问。你的任务是基于下面提供的环境条件，为用户推荐最适合种植的作物品种，并提供初步的种植计划。

**当前环境条件分析:**
*   **地理位置 (region):** {context.get('region', '未提供')}
*   **日照时长 (suntime):** {context.get('suntime', '未提供')} 小时/天
*   **空气湿度 (humidity):** {context.get('humidity', '未提供')} %
*   **土壤pH值 (soilpH):** {context.get('soilpH', '未提供')}

**处理要求:**
1.  **品种匹配:** 根据以上所有条件，从你的知识库中筛选出至少五种最匹配的候选作物品种。
2.  **量化评估:** 为每种候选作物给出一个综合“推荐指数”（0-100分），并解释打分依据。
3.  **方案优选:** 选出推荐指数最高的**三种**作物。
4.  **初步计划:** 为这三种优选作物，分别提供一个简洁的、包含核心要点（浇水频率、施肥建议、光照管理）的初步种植计划。
5.  **格式要求:** 使用Markdown格式，让报告清晰易读。报告结尾不要有署名和日期。

User: 基于以上条件，请给出详细的作物推荐与种植计划报告。
"""
    result1 = call_text_model(prompt1, 'qwen-plus', temperature=0.64)

    prompt2 = f"""
System: 你是一位资深的农业规划师，擅长组合种植策略。现在，请你基于以下这份【单一作物推荐报告】，进行深度分析，提出组合种植方案。

**【单一作物推荐报告】:**
---
{result1}
---

**处理要求:**
1.  **组合分析:** 分析报告中推荐的三种作物进行两两组合或三者组合种植的可能性，评估其共生性（互利/互斥）。
2.  **方案对比:** 给出1-2个最有潜力的组合种植方案，并与单一作物种植进行对比，分析其优缺点（如空间利用率、抗病虫害能力、产量多样性等）。
3.  **最终建议:** 综合所有分析，给出最终的、Top 3的种植选择（可以是单一作物，也可以是组合方案），并为每个选择附上一个更详细的、可操作的种植计划（例如，可以细化到每周的关键任务）。
4.  **格式要求:** 使用Markdown格式，让报告清晰易读。报告结尾不要有署名和日期。

User: 请对以上报告进行组合分析，并给出最终的种植建议。
"""
    final_result = call_text_model(prompt2, 'qwen-plus', temperature=0.45)

   
    mem_extraction_prompt = f'从以下最终建议中，提取出所有被推荐的作物品种的名称。以JSON数组格式返回，键为 "recommended_crops"。\n\n文本：\n{final_result}'
    crops_str = call_text_model(mem_extraction_prompt, 'qwen-turbo')
    crops_data = extract_json_from_text(crops_str)
    
    if crops_data and 'recommended_crops' in crops_data:
        # 使用标准化的参数名写入context
        context['recommended_crops'] = crops_data['recommended_crops']
      
        if crops_data['recommended_crops']:
            context['crop_type'] = crops_data['recommended_crops'][0]
        print(f"记忆更新 [模式A-作物]: recommended_crops -> {context.get('recommended_crops')}, crop_type -> {context.get('crop_type')}")
        return final_result, None        



def run_workflow_B(context):
    """Part B: 病害诊断 (V6 - 恢复当前输入优先的设计)"""
    user_input = context.get('user_input', '')
    local_image_path = context.get('local_image_path')
    
   
    known_crop_type_from_history = context.get('crop_type', None)

    
    # 组合查询时，让当前输入占主导
    combined_query = user_input
    if known_crop_type_from_history:
        # 将历史作物作为一个补充关键词，而不是强制组合
        combined_query += f" {known_crop_type_from_history}"
    
    print(f"模式B - 组合查询关键词: {combined_query}")

    docs_text = "---本地知识库参考---\n"
    if not df_disease.empty and combined_query:
        keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', combined_query)
        added_diseases = set()
        for kw in keywords:
            if len(kw) > 1:
                try:
                    results_symptom = df_disease[df_disease['叶片症状'].astype(str).str.contains(kw, na=False, case=False)]
                    results_name = df_disease[df_disease['病害名称'].astype(str).str.contains(kw, na=False, case=False)]
                    results = pd.concat([results_symptom, results_name]).drop_duplicates()
                    for _, row in results.iterrows():
                        if row['病害ID'] not in added_diseases:
                            docs_text += row.to_frame().T.to_markdown(index=False) + "\n\n"
                            added_diseases.add(row['病害ID'])
                except Exception as e:
                    print(f"在病害库中搜索'{kw}'时出错: {e}")

    if 'added_diseases' not in locals() or len(added_diseases) == 0:
        docs_text += "在本地知识库中未检索到与当前问题直接相关的信息。\n"

   
    prompt = f"""
# 角色
你是一位顶级的农业图像诊断专家。你的分析必须以【事实为依据】，即以用户上传的图片为最优先的判断标准。

## 分析任务
你的任务是根据用户上传的图片和附带的文字描述，进行详细的病害诊断。

## 已知参考信息
*   **用户当前问题:** "{user_input}"
*   **历史对话中可能相关的作物:** `{known_crop_type_from_history or '无'}` (此信息仅供参考，如果与图片内容冲突，必须以图片为准！)
*   **本地知识库参考:** 
{docs_text}

## 核心工作流程
1.  **【图像优先分析】:** 这是你最重要的任务！请首先、且仅仅基于我上传的图片，详细描述你看到的植物和病征。**明确说明你从图片中识别出的植物是什么类型**。
2.  **【信息整合与诊断】:** 在完成独立的图像分析后，结合你识别出的植物类型、用户的问题描述、以及所有参考信息，给出1-3个最可能的诊断推测。如果历史作物 `{known_crop_type_from_history or '无'}` 与你从图片中识别出的不符，请明确指出这一点。
3.  **【提供建议与追问】:** 针对你认为最可信的诊断，提供初步的防治措施，并在最后提出需要用户补充信息的问题。

# 用户指令
请严格遵循以上工作流程，以图片内容为最高优先级，进行诊断。
"""
    final_result = call_vl_model(prompt, local_image_path)

    
    mem_extraction_prompt = f'从以下诊断报告中，提取出最主要的【病害或问题名称】和它所影响的【作物种类】。以JSON格式返回，键为 "diagnosed_issue" 和 "crop_type"。\n\n报告：\n{final_result}'
    extracted_info_str = call_text_model(mem_extraction_prompt, 'qwen-turbo')
    extracted_info = extract_json_from_text(extracted_info_str)
    
    if extracted_info:
        # 用新诊断出的问题覆盖旧的
        if extracted_info.get('diagnosed_issue'):
            context['diagnosed_issue'] = extracted_info.get('diagnosed_issue')
            print(f"记忆更新 [模式B-问题]: diagnosed_issue -> {context.get('diagnosed_issue')}")
        
        # 用本次从图片中新识别出的作物，覆盖掉旧的crop_type
        if extracted_info.get('crop_type'):
            context['crop_type'] = extracted_info.get('crop_type')
            print(f"记忆更新 [模式B-作物]: crop_type -> {context.get('crop_type')} (已覆盖旧值)")

    return final_result, None
def run_workflow_C(context):
    """Part C: 市场分析 (V5.1 - 完整RAG与标准化参数)"""
    user_query = context.get('user_input', '')
    local_image_path = context.get('local_image_path')
    
   
    known_crop_type = context.get('crop_type', '用户在图片中展示的作物')
    known_region = context.get('region', '用户所在地区')

    
    def search_kb(df, columns, query):
        if df.empty or not query:
            return "知识库未加载或查询为空。"
        
        keywords = re.findall(r'[\u4e00-\u9fa5]+', query)
        if not keywords:
            return "查询中未找到有效关键词。"
            
        combined_results = []
        for col in columns:
            if col in df.columns:
                for kw in keywords:
                    if len(kw) > 1: # 避免搜索单个字符
                        try:
                            results = df[df[col].str.contains(kw, na=False)]
                            combined_results.append(results)
                        except Exception as e:
                            print(f"在列'{col}'中搜索'{kw}'时出错: {e}")
                            
        if combined_results:
            # 合并所有结果，去除重复项，并取前5条
            return pd.concat(combined_results).drop_duplicates().head(5).to_markdown(index=False)
        return "在知识库中未检索到直接相关信息。"

    # 对三个知识库进行检索
    kb1_result = search_kb(df_variety, ['品种名称', '类型'], user_query)
    kb2_result = search_kb(df_nutrient, ['叶片症状', '缺乏元素'], user_query)
    kb3_result = search_kb(df_disease, ['病害名称', '叶片症状'], user_query)
    
    # 整合所有RAG结果
    full_rag_text = f"""
--- 基础品种信息表 (KB1) ---
{kb1_result}
--- 营养缺乏症状表 (KB2) ---
{kb2_result}
--- 病害特征表 (KB3) ---
{kb3_result}
"""

    
    prompt_yield = f"""
# 角色
你是一名农业遥感与产量评估专家。

## 已知背景信息
*   **用户核心诉求:** "{user_query}"
*   **待分析作物种类 (来自历史对话):** {known_crop_type}
*   **作物所在地区 (来自历史对话):** {known_region}
*   **相关知识库信息 (基于用户问题检索):**
{full_rag_text}

## 任务：产量分析报告
你的任务是基于我上传的农田俯拍图，结合以上所有背景信息，撰写一份详细的【产量分析报告】。

### 分析步骤
1.  **作物识别与确认:** 首先，确认图片中的作物是否与已知的“{known_crop_type}”一致。如果不一致，请以图片内容为准进行分析。尤其要注意，图片中可能有不止一种作物，会出现多种作物组合间种的情况，要对组合中每种作物都进行评估。可以参考【知识库信息】辅助识别。
2.  **生长阶段与健康状况评估:** 判断作物当前的生长阶段（如苗期、开花期、结果期）及其整体健康状况（颜色是否正常、有无明显病虫害迹象）。可以参考【知识库信息】中的病害和营养缺乏症状。
3.  **种植密度估算:** 估算田间的种植密度（例如：株/平方米）。
4.  **产量预测:** 综合以上所有信息，对该片农田的**单产（公斤/亩）**和**总产量（吨）**进行合理预测，并给出预测的数据范围（例如：总产量预计在2.5-3.0吨之间）。

User: 请根据我上传的图片和以上信息，开始撰写【产量分析报告】。
"""
    result_yield_analysis = call_vl_model(prompt_yield, local_image_path)
    
    
    prompt_profit = f"""
# 角色
你是一名专业的农业经济分析师。

## 已知背景信息
*   **用户核心诉求:** "{user_query}"
*   **分析对象:** 基于以下【产量分析报告】中的作物。
*   **作物所在地区 (用于市场定价参考):** {known_region}

## 【产量分析报告】
---
{result_yield_analysis}
---

## 任务：利润分析报告
你的任务是基于以上【产量分析报告】，结合市场行情，撰写一份【利润分析报告】。

### 分析步骤
1.  **市场价格评估:** 根据“{known_region}”的近期市场数据，评估报告中所述作物的当前市场批发价格（元/公斤）。
2.  **总收入估算:** 利用报告中的【总产量】和市场价格，计算出预估的总销售收入。
3.  **成本扣除 (估算):** 估算并扣除常见的成本项（如种子、肥料、人工、运输、销售渠道费用等），给出一个大致的成本范围。
4.  **净利润预测:** 计算出最终的**预估净利润（元）**，并提供一个合理的利润区间。

User: 请基于以上报告和信息，继续撰写【利润分析报告】。
"""
    result_profit_analysis = call_text_model(prompt_profit, 'qwen-max', temperature=0.82)
    
    
    mem_extraction_prompt = f'从以下两份报告中，提取出【预估总产量(吨)】和【预估净收益(元)】这两个数值。以JSON格式返回，键为 "estimated_yield_tons" 和 "estimated_net_profit_cny"。\n\n产率报告：{result_yield_analysis}\n\n利润报告：{result_profit_analysis}'
    extracted_info_str = call_text_model(mem_extraction_prompt, 'qwen-turbo')
    extracted_info = extract_json_from_text(extracted_info_str)
    
    if extracted_info:
        # 使用update，会用新值覆盖旧值
        context.update(extracted_info)
        print(f"记忆更新 [模式C-经济]: {extracted_info}")

    final_result = f"--- **产量分析报告** ---\n{result_yield_analysis}\n\n--- **利润分析报告** ---\n{result_profit_analysis}"
    return final_result, None
def run_workflow_D(context):
    """Part D: 产品推广 (V5 - 全参数化与深度上下文感知版)"""
    user_input = context.get('user_input', '')
    
    
    param_extraction_prompt = f"""你是一个任务分析助手。请分析用户的推广请求，并提取出他明确想要推广的【作物品种】。如果用户明确提到了具体品种，比如“帮我推广一下我的阳光玫瑰葡萄”，请只提取这个品种。如果用户只是模糊地说“帮我写个广告”或“就刚才那个”，则没有明确指定品种。请以严格的JSON格式返回，格式为：{{"crop_type_specified": "用户指定的品种名称或null"}}。用户请求: "{user_input}" """
    params_str = call_text_model(param_extraction_prompt, 'qwen-turbo')
    extracted_params = extract_json_from_text(params_str) or {}
    
    
    final_crop_type = None
    
    if extracted_params.get('crop_type_specified'):
        final_crop_type = extracted_params['crop_type_specified']
        context['crop_type'] = final_crop_type # 立刻更新上下文中的核心作物，确保后续一致
        print(f"决策[模式D]: 使用用户本次指定的品种 -> {final_crop_type}")

   
    elif context.get('crop_type'):
        final_crop_type = context.get('crop_type')
        print(f"决策[模式D]: 继承上下文中的核心品种 -> {final_crop_type}")

   
    elif context.get('recommended_crops') and context['recommended_crops']:
        final_crop_type = context.get('recommended_crops')[0]
        context['crop_type'] = final_crop_type # 更新上下文，明确核心作物
        print(f"决策[模式D]: 使用推荐列表的第一个品种 -> {final_crop_type}")
        
    else:
        # 如果以上全都没有，则无法继续
        return "请先告诉我您想推广什么产品，或者先通过其他模式让我了解一下您的作物。", None

   
    
    promo_context = {
        'crop_type': final_crop_type,
        
        # --- 营销相关参数 (可由用户在未来扩展) ---
        'name': context.get('name', '当季鲜品推广'),
        'target_audience': context.get('target_audience', '追求高品质生活的消费者'),
        'promotion_channel': context.get('promotion_channel', '社交媒体与线上内容平台'),
        
        # --- 从模式A继承的环境参数 ---
        'weather_conditions': f"日照{context.get('suntime', '充足')}小时/天, 湿度{context.get('humidity', '适中')}%",
        'soil_humidity_info': f"土壤pH值{context.get('soilpH', '适中')}",
        
        # --- 从模式B继承的健康状况参数 ---
        # 如果模式B诊断出了问题，就用问题；否则，就用默认的健康描述
        'health_status': context.get('diagnosed_issue', '植株健康，果实饱满无病害'),
        
        # --- 通用或可扩展的参数 ---
        'growth_stage': context.get('growth_stage', '完熟期，新鲜采摘'),
        'additional_notes': context.get('additional_notes', '采用物理防虫，不使用化学农药')
    }
    
    # 将构建好的上下文，格式化为字符串，方便注入到Prompt中 (此部分逻辑不变)
    shared_params_str = "\n".join([f"*   **{key.replace('_', ' ').title()}:** {value}" for key, value in promo_context.items()])


    prompt_image_gen = f"""
System: 你是一位兼具营销洞察与视觉创意的提示词（Prompt）设计大师。你的任务是根据下面提供的详细营销背景和产品信息，为AI文生图模型（如通义万相）构思一段高质量的【中文提示词】。

**你的首要任务：** 生成的提示词必须清晰、准确地将主体农作物 **“{promo_context.get('crop_type', '未指定作物')}”** 作为画面的绝对核心。

**当前营销与产品背景：**
{shared_params_str}

**构思指令：**
1.  **【核心】明确主体:** 提示词必须围绕 **“{promo_context.get('crop_type', '未指定作物')}”** 展开，使用具体、生动的描述让AI毫无歧义地识别要画什么。
2.  **【视觉化产品特性】:** 将产品的 **“{promo_context.get('growth_stage', '完熟')}”** 状态和 **“{promo_context.get('health_status', '健康饱满')}”** 的特征转化为具体的视觉元素。
3.  **【融合营销概念】:** 设计的画面需要能够吸引我们的目标受众——**“{promo_context.get('target_audience', '消费者')}”**，并要符合在 **“{promo_context.get('promotion_channel', '社交媒体')}”** 上传播的视觉风格。整个画面的感觉要契合 **“{promo_context.get('name', '产品推广')}”** 这个活动主题。
4.  **【营造场景氛围】:** 根据 **“{promo_context.get('weather_conditions', '良好天气')}”** 等环境信息，构建一个能最好衬托出 **“{promo_context.get('crop_type', '该产品')}”** 的背景、光线和氛围。
5.  **【注入独特卖点】:** 如果可能，通过视觉元素巧妙地暗示 **“{promo_context.get('additional_notes', '天然')}”** 这个独特卖点。

User: 请根据以上所有信息，生成最终的【中文提示词】。
"""
    image_prompt = call_text_model(prompt_image_gen, 'deepseek-v3', temperature=0.85)
    
    
    prompt_text_gen = f"""
System: 你是一位顶级的农产品营销策划与文案撰稿专家。你的任务是根据下面提供的详细营销背景和产品信息，创作一篇具有高度吸引力和转化潜力的【中文推广文案】。

**你的基础要求：** 在文案中，必须始终清晰、准确地使用产品名称 **“{promo_context.get('crop_type', '该农产品')}”**。

**当前营销与产品背景：**
{shared_params_str}

**撰写指令：**
1.  **【核心】精准指代:** 在整篇文案中，必须反复、明确地使用 **“{promo_context.get('crop_type', '该农产品')}”** 这个具体名称。
2.  **【受众导向】:** 文案的语气、风格和卖点选择，必须精准对标我们的目标客户——**“{promo_context.get('target_audience', '消费者')}”**。
3.  **【渠道适配】:** 文案的篇幅、结构和形式，要适合在 **“{promo_context.get('promotion_channel', '社交媒体')}”** 上发布。
4.  **【转化产品特点为用户利益】:**
    *   将 **“{promo_context.get('weather_conditions', '优越的环境')}”** 和 **“{promo_context.get('health_status', '健康的植株')}”** 转化为消费者能感受到的卓越品质。
    *   将 **“{promo_context.get('growth_stage', '完熟期')}”** 这个信息，转化为对产品新鲜度、最佳赏味期的承诺。
    *   重点突出 **“{promo_context.get('additional_notes', '天然种植')}”** 这个核心卖点。
5.  **【融入活动背景】:** 文案的整体基调要与 **“{promo_context.get('name', '本次活动')}”** 的主题保持一致。

User: 请根据以上所有信息，撰写最终的【中文推广文案】。
"""
    docs_text = call_text_model(prompt_text_gen, 'deepseek-v3', temperature=0.85)

    

    
    image_url = call_image_model(image_prompt)
    
    
    # 将本次推广的核心信息存入记忆
    if promo_context:
        context['last_promotion'] = {
            'crop_type': promo_context.get('crop_type'),
            'name': promo_context.get('name'),
            'target_audience': promo_context.get('target_audience')
        }
        print(f"记忆更新 [模式D]: 上次推广活动 -> {context['last_promotion']}")

    return docs_text, image_url

@app.route('/')
def login_page():
    session.clear(); return render_template('login.html')

@app.route('/main')
def main_page():
   
    session.clear() 
    print("页面刷新，会话已清空，所有记忆已重置。")
    
    # 确保 session 字典存在
    session.permanent = True
    if 'context' not in session:
        session['context'] = {}
        
    return render_template('main.html')


@app.route('/api/chat', methods=['POST'])
def chat_api():
    if 'context' not in session:
        session['context'] = {}

    try:
        context = session.get('context', {})
        context['user_input'] = request.form.get('userInput', '')
        mode = request.form.get('currentMode', 'A')

        local_filepath = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '':
                filename = secure_filename(f"{int(time.time())}_{file.filename}")
                local_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(local_filepath)
                print(f"图片已保存到本地路径: {local_filepath}")
                context['local_image_path'] = local_filepath

        workflow_functions = {'A': run_workflow_A, 'B': run_workflow_B, 'C': run_workflow_C, 'D': run_workflow_D}
        workflow_func = workflow_functions.get(mode)
        
        ai_reply_text = "未知的模式或内部错误"
        ai_image_gen_url = None

        if workflow_func:
            
            result = workflow_func(context)
            # 检查result是否是一个可以安全解包的元组
            if isinstance(result, tuple) and len(result) == 2:
                ai_reply_text, ai_image_gen_url = result
            elif isinstance(result, str): # 如果只返回了一个字符串
                ai_reply_text = result
                ai_image_gen_url = None
            else:
                # 如果返回了None或者其他意外类型，记录错误并使用默认值
                print(f"警告: 工作流函数 (模式: {mode}) 返回了意外的类型: {type(result)}")
                ai_reply_text = "抱歉，处理您的请求时发生内部错误，工作流未返回有效结果。"

        # 更新 session
        session['context'] = context
        session.modified = True
        
        return jsonify({
            'text': ai_reply_text,
            'imageUrl': ai_image_gen_url,
            # 将更新后的完整上下文返回给前端
            'updatedContext': context 
        })

    except Exception as e:
        # 打印详细的traceback，便于调试
        import traceback
        traceback.print_exc()
        print(f"在chat_api中发生严重错误: {e}")
        return jsonify({'text': f'服务器内部错误: {e}', 'imageUrl': None}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)