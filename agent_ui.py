import streamlit as st
import requests
import json
import os
import re

st.set_page_config(
    page_title="AI Agent UI",
    page_icon="🤖",
    layout="wide"
)

st.title("AI Agent 智能交互界面")

st.sidebar.title("模型配置")
demo_mode = st.sidebar.checkbox("演示模式（无需 API Key）", value=True)
api_key = st.sidebar.text_input("API Key", type="password")
model = st.sidebar.selectbox("模型选择", ["deepseek-chat", "gpt-3.5-turbo", "gpt-4"])
endpoint = st.sidebar.text_input("API Endpoint", value="https://api.deepseek.com/v1/chat/completions")

if demo_mode:
    client = "demo"
    st.sidebar.success("演示模式已启用，无需 API Key")
elif api_key:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=endpoint
        )
    except Exception as e:
        client = None
        st.warning(f"无法初始化 OpenAI 客户端: {str(e)}")
else:
    client = None
    st.warning("请在侧边栏输入 API Key 以使用大模型功能，或启用演示模式")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

CPP_SERVER = "http://127.0.0.1:8080/execute_task"

def send_to_cpp(action, value=0.0, extra_params=None):
    payload = {"action": action, "value": value}
    if extra_params:
        payload.update(extra_params)
    try:
        resp = requests.post(CPP_SERVER, headers={"Content-Type": "application/json"}, json=payload, timeout=10)
        if resp.status_code == 200:
            return True, "指令发送成功！分析结果将在 3D 视图中高亮显示。"
        else:
            return False, f"指令发送失败：{resp.text}"
    except requests.exceptions.Timeout:
        return False, "连接 C++ 程序超时，请检查 test_render.exe 是否运行。"
    except requests.exceptions.ConnectionError:
        try:
            resp = requests.post("http://localhost:8080/execute_task", headers={"Content-Type": "application/json"}, json=payload, timeout=10)
            if resp.status_code == 200:
                return True, "指令发送成功！分析结果将在 3D 视图中高亮显示。"
            else:
                return False, f"指令发送失败：{resp.text}"
        except Exception as e2:
            return False, f"连接 C++ 程序失败：{str(e2)}"
    except Exception as e:
        return False, f"连接 C++ 程序失败：{str(e)}"

def parse_user_intent(prompt):
    prompt_lower = prompt.lower()
    
    curved_keywords = ["曲面", "曲线", "弯曲", "弧面", "弧形", "圆弧", "圆面", "球面", "圆柱", "凸面", "凹面", "curved", "curve", "surface"]
    sharp_keywords = ["锐角", "尖角", "棱角", "锐边", "尖边", "折角", "棱边", "sharp", "edge", "corner"]
    flat_keywords = ["平面", "平坦", "平整", "flat", "planar", "level"]
    thin_keywords = ["薄弱", "薄", "厚度", "thin", "thickness", "wall"]
    highlight_keywords = ["高亮", "标出", "显示", "找出", "找到", "查找", "搜索", "定位", "识别", "检测", "highlight", "find", "show", "detect"]
    
    is_curved = any(kw in prompt_lower for kw in curved_keywords)
    is_sharp = any(kw in prompt_lower for kw in sharp_keywords)
    is_flat = any(kw in prompt_lower for kw in flat_keywords)
    is_thin = any(kw in prompt_lower for kw in thin_keywords)
    
    if is_curved and not is_sharp and not is_flat:
        threshold = 0.05
        match = re.search(r'([0-9]+(\.[0-9]+)?)', prompt)
        if match:
            threshold = float(match.group(1))
        return "find_curved_surfaces", threshold, f"正在查找模型中的曲面/曲线区域（曲率阈值={threshold}）..."
    
    if is_sharp and not is_curved and not is_flat:
        angle = 30.0
        match = re.search(r'([0-9]+(\.[0-9]+)?)', prompt)
        if match:
            angle = float(match.group(1))
        return "find_sharp_edges", angle, f"正在查找模型中的锐角/棱边区域（角度阈值={angle}°）..."
    
    if is_flat and not is_curved and not is_sharp:
        threshold = 0.1
        match = re.search(r'([0-9]+(\.[0-9]+)?)', prompt)
        if match:
            threshold = float(match.group(1))
        return "find_flat_surfaces", threshold, f"正在查找模型中的平面区域（平坦度阈值={threshold}）..."
    
    if is_thin:
        threshold = 1.0
        match = re.search(r'(?:小于|设为|阈值为|厚度为)([0-9]+(\.[0-9]+)?)mm', prompt)
        if match:
            threshold = float(match.group(1))
        elif re.search(r'[0-9]+(\.[0-9]+)?mm', prompt):
            match = re.search(r'([0-9]+(\.[0-9]+)?)mm', prompt)
            if match:
                threshold = float(match.group(1))
        return "check_thickness", threshold, f"正在分析模型中厚度小于 {threshold}mm 的薄弱部位..."
    
    if any(kw in prompt_lower for kw in highlight_keywords):
        if is_curved:
            return "find_curved_surfaces", 0.05, "正在查找模型中的曲面/曲线区域..."
        if is_sharp:
            return "find_sharp_edges", 30.0, "正在查找模型中的锐角/棱边区域..."
        if is_flat:
            return "find_flat_surfaces", 0.1, "正在查找模型中的平面区域..."
        return "find_curved_surfaces", 0.05, "正在查找模型中的曲面/曲线区域..."
    
    if any(kw in prompt_lower for kw in ["特征", "分析", "结构", "feature", "analyze", "structure"]):
        return "find_curved_surfaces", 0.05, "正在分析模型特征，查找曲面/曲线区域..."
    
    return "find_curved_surfaces", 0.05, "正在查找模型中的曲面/曲线区域..."

if prompt := st.chat_input("请输入指令，例如：找出模型中的曲面，或查找薄弱部位"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    if not client:
        with st.chat_message("assistant"):
            st.markdown("请在侧边栏输入 API Key 以使用大模型功能，或启用演示模式")
    elif client == "demo":
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            action, value, description = parse_user_intent(prompt)
            
            full_response += description + "\n"
            message_placeholder.markdown(full_response)
            
            success, msg = send_to_cpp(action, value)
            if success:
                full_response += f"✅ {msg}"
            else:
                full_response += f"❌ {msg}"
            
            message_placeholder.markdown(full_response)
        
        st.session_state.messages.append({"role": "assistant", "content": full_response})
    else:
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            try:
                from openai import OpenAI
                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": "analyze_model_thickness",
                            "description": "分析模型中厚度小于指定阈值的薄弱部位",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "threshold": {"type": "number", "description": "厚度阈值（毫米）"}
                                },
                                "required": ["threshold"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "find_curved_surfaces",
                            "description": "查找模型中的曲面或曲线区域并高亮显示",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "curvature_threshold": {"type": "number", "description": "曲率阈值（0-1之间，越大越弯曲）"}
                                },
                                "required": ["curvature_threshold"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "find_sharp_edges",
                            "description": "查找模型中的锐角或棱边区域并高亮显示",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "angle_threshold": {"type": "number", "description": "角度阈值（度数）"}
                                },
                                "required": ["angle_threshold"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "find_flat_surfaces",
                            "description": "查找模型中的平面或平坦区域并高亮显示",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "flatness_threshold": {"type": "number", "description": "平坦度阈值（0-1之间，越小越平坦）"}
                                },
                                "required": ["flatness_threshold"]
                            }
                        }
                    }
                ]
                
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是一个3D模型分析助手。当用户要求分析模型时，使用合适的工具。支持的功能：1)分析薄弱部位(analyze_model_thickness) 2)查找曲面/曲线(find_curved_surfaces) 3)查找锐角/棱边(find_sharp_edges) 4)查找平面(find_flat_surfaces)"},
                        {"role": "user", "content": prompt}
                    ],
                    tools=tools,
                    tool_choice="auto"
                )
                
                if response.choices[0].message.tool_calls:
                    tool_calls = response.choices[0].message.tool_calls
                    for tool_call in tool_calls:
                        args = json.loads(tool_call.function.arguments)
                        
                        if tool_call.function.name == "analyze_model_thickness":
                            threshold = args.get("threshold", 1.0)
                            full_response += f"正在分析模型中厚度小于 {threshold}mm 的薄弱部位...\n"
                            message_placeholder.markdown(full_response)
                            success, msg = send_to_cpp("check_thickness", threshold)
                            
                        elif tool_call.function.name == "find_curved_surfaces":
                            threshold = args.get("curvature_threshold", 0.3)
                            full_response += f"正在查找模型中的曲面/曲线区域（曲率阈值={threshold}）...\n"
                            message_placeholder.markdown(full_response)
                            success, msg = send_to_cpp("find_curved_surfaces", threshold)
                            
                        elif tool_call.function.name == "find_sharp_edges":
                            angle = args.get("angle_threshold", 30.0)
                            full_response += f"正在查找模型中的锐角/棱边区域（角度阈值={angle}°）...\n"
                            message_placeholder.markdown(full_response)
                            success, msg = send_to_cpp("find_sharp_edges", angle)
                            
                        elif tool_call.function.name == "find_flat_surfaces":
                            threshold = args.get("flatness_threshold", 0.1)
                            full_response += f"正在查找模型中的平面区域（平坦度阈值={threshold}）...\n"
                            message_placeholder.markdown(full_response)
                            success, msg = send_to_cpp("find_flat_surfaces", threshold)
                        else:
                            success, msg = False, "未知工具调用"
                        
                        if success:
                            full_response += f"✅ {msg}"
                        else:
                            full_response += f"❌ {msg}"
                else:
                    full_response = response.choices[0].message.content or ""
            except Exception as e:
                full_response = f"❌ 调用大模型失败：{str(e)}"
            
            message_placeholder.markdown(full_response)
        
        st.session_state.messages.append({"role": "assistant", "content": full_response})

st.sidebar.title("系统状态")
if st.sidebar.button("检查 C++ 服务状态"):
    try:
        response = requests.get("http://127.0.0.1:8080", timeout=3)
        st.sidebar.success("✅ C++ 服务运行正常")
    except Exception:
        try:
            response = requests.get("http://localhost:8080", timeout=3)
            st.sidebar.success("✅ C++ 服务运行正常")
        except Exception as e:
            st.sidebar.error(f"❌ C++ 服务未运行：{str(e)}")

st.sidebar.title("使用说明")
st.sidebar.markdown("1. 启动 test_render.exe 并加载 STL 模型")
st.sidebar.markdown("2. 在聊天输入框中输入自然语言指令")
st.sidebar.markdown("3. 系统会自动分析指令并调用相应工具")
st.sidebar.markdown("4. 分析结果会在 3D 视图中高亮显示")
st.sidebar.markdown("\n示例指令：")
st.sidebar.markdown("- 找出模型中的曲面")
st.sidebar.markdown("- 查找模型中的曲线并高亮")
st.sidebar.markdown("- 找出模型中的锐角棱边")
st.sidebar.markdown("- 查找模型中的平面区域")
st.sidebar.markdown("- 帮我找出厚度小于1mm的薄弱部位")
st.sidebar.markdown("- 分析模型中的弯曲部分")
