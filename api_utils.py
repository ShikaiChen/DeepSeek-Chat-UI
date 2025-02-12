# api_utils.py
import requests
from openai import OpenAI
import streamlit as st
from db_utils import conn, c

def web_search(query, api_key):
    """执行谷歌搜索并返回格式化结果"""
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {
        "q": query,
        "gl": "cn",
        "hl": "zh-cn",
        "num": 5  # 获取前5条结果
    }

    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers=headers,
            json=payload,
            timeout=10
        )
        results = response.json()

        search_context = "\n".join([
            f"• [{item['title']}]({item['link']})\n  {item['snippet']}"
            for item in results.get("organic", [])[:3]  # 取前3条结果
        ])
        return f"**网络搜索结果**\n{search_context}\n\n"

    except Exception as e:
        st.error(f"搜索失败: {str(e)}")
        return ""

def get_active_api_config():
    """获取当前激活的API配置"""
    c.execute("""
        SELECT base_url, api_key, model_name 
        FROM api_configurations 
        WHERE is_active = 1 
        LIMIT 1
    """)
    result = c.fetchone()
    return result or ("https://api.deepseek.com/v1", "", "deepseek-r1")

def process_thinking_phase(stream, used_key):
    """处理模型思考阶段"""
    thinking_content = ""
    with st.status("思考中...", expanded=True) as status:
        placeholder = st.empty()
        for chunk in stream:
            content = chunk.choices[0].delta.reasoning_content or ""
            thinking_content += content

            # 计算并更新token使用
            adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in content)
            c.execute("""
                UPDATE api_keys 
                SET used_tokens = used_tokens + ? 
                WHERE key = ?
            """, (adjusted_length, used_key))
            conn.commit()

            placeholder.markdown(f"```\n{thinking_content}\n```")

            if not content:  # 结束标志
                status.update(label="思考完成", state="complete", expanded=False)

    return f"<THINKING>\n{thinking_content}\n</THINKING>\n"

def process_response_phase(stream, used_key):
    """处理模型响应阶段"""
    response_content = ""
    placeholder = st.empty()
    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        response_content += content

        # 计算并更新token使用
        adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in content)
        c.execute("""
            UPDATE api_keys 
            SET used_tokens = used_tokens + ? 
            WHERE key = ?
        """, (adjusted_length, used_key))
        conn.commit()

        placeholder.markdown(response_content + "▌")

    placeholder.markdown(response_content)
    return response_content
