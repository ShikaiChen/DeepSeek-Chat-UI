import base64
import re
import streamlit as st
import os
import sqlite3
import bcrypt
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import tempfile
from typing import Dict, List, Union
import hashlib
import io
import textract 
import re
import requests

# 加载环境变量
load_dotenv()

# 数据库初始化
conn = sqlite3.connect('app.db')
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    session_id TEXT UNIQUE,
    session_name TEXT,
    session_data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

# 创建表
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password_hash TEXT,
    is_admin BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,
    username TEXT,
    used_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()

def web_search(query: str, api_key: str) -> str:
    headers = {
        'X-API-KEY': search_key,
        'Content-Type': 'application/json'
    }
    payload = {
        "q": query,
        "gl": "cn",
        "hl": "zh-cn",
        "num": 10  # 获取前5条结果
    }
    response = requests.post('https://google.serper.dev/search', 
                           headers=headers,
                           json=payload)
    results = response.json()
    
    # 提取核心内容
    search_context = "\n".join([
        f"来源：{item['link']}\n内容：{item['snippet']}" 
        for item in results.get('organic', [])
    ])
    return f"[网络搜索结果]\n{search_context}\n"

def save_uploaded_files(uploaded_files) -> List[Dict]:
    """保存上传的文件到临时目录并返回文件信息"""
    saved_files = []
    now_name_list = [file['name'] for file in st.session_state.uploaded_files]
    for file in uploaded_files:
        # 检查文件大小（1MB限制）
        if (file.name in now_name_list):
            continue
        if file.size > 1 * 1024 * 1024:
            # st.error(f"文件 {file.name} 大小超过1MB限制")
            continue

        # 读取文件内容
        try:
            if file.name.endswith(('.doc', '.docx', 'pdf')):
                # 使用 textract 解析二进制文件流
                file_path = os.path.join(dirs, file.name)
                # 将文件保存到本地文件系统
                with open(file_path, "wb") as f:
                    f.write(file.getvalue())
                content = textract.process(dirs + file.name).decode("utf-8")
            else:
                content = file.getvalue().decode("utf-8")
                continue
        except UnicodeDecodeError:
            st.error(f"文件 {file.name} 包含非文本内容，请上传纯文本文件")
            continue

        # 生成内容哈希值
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # 检查是否已存在相同内容
        if any(f["hash"] == content_hash for f in st.session_state.uploaded_files):
            # st.error(f"文件 {file.name} 内容已存在，跳过上传")
            continue

        saved_files.append({
            "name": file.name,
            "content": content,
            "size": file.size,
            "hash": content_hash
        })
    return saved_files

def format_file_contents(files: List[Dict]) -> str:
    """将文件内容格式化为带分隔符的字符串"""
    formatted = []
    for file in files:
        formatted.append(f"=== {file['name']} ===\n{file['content']}\n")
    return "\n".join(formatted)

# 辅助函数
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def is_blacklisted(username):
    c.execute('SELECT 1 FROM blacklist WHERE username = ?', (username,))
    return c.fetchone() is not None

def save_session():
    if st.session_state.get('valid_key') and 'current_session_id' in st.session_state:
        try:
            username = c.execute('SELECT username FROM api_keys WHERE key = ?', 
                               (st.session_state.used_key,)).fetchone()[0]
            session_data = json.dumps(st.session_state.messages)

            c.execute('''
                INSERT INTO history (username, session_id, session_name, session_data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    session_data = excluded.session_data,
                    updated_at = CURRENT_TIMESTAMP
            ''', (
                username,
                st.session_state.current_session_id,
                f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                session_data
            ))

            # 保持最多10条记录
            c.execute('''
                DELETE FROM history 
                WHERE id NOT IN (
                    SELECT id FROM history 
                    WHERE username = ? 
                    ORDER BY updated_at DESC 
                    LIMIT 10
                )
            ''', (username,))
            conn.commit()
        except Exception as e:
            st.error(f"保存会话失败: {str(e)}")


def load_session(session_id):
    try:
        c.execute('SELECT session_data FROM history WHERE session_id = ?', (session_id,))
        if data := c.fetchone():
            st.session_state.messages = json.loads(data[0])
            st.session_state.current_session_id = session_id
            st.rerun()
    except Exception as e:
        st.error(f"加载会话失败: {str(e)}")

# 用户认证模块
def login_form():
    with st.form("Login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if is_blacklisted(username):
                st.error("This username is blacklisted")
                return
            elif authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid credentials")

def authenticate_user(username, password):
    c.execute('SELECT password_hash, is_admin FROM users WHERE username = ?', (username,))
    result = c.fetchone()
    if result and verify_password(password, result[0]):
        st.session_state.is_admin = bool(result[1])
        return True
    return False

def register_form():
    with st.form("Register"):
        username = st.text_input("New Username")
        password = st.text_input("New Password", type="password")
        if st.form_submit_button("Register"):
            if is_blacklisted(username):
                st.error("This username is blacklisted")
                return
            try:
                c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                         (username, hash_password(password)))
                conn.commit()
                st.success("Registration successful! Please login")
            except sqlite3.IntegrityError:
                st.error("Username already exists")
    
# 管理员功能模块
def admin_panel():
    if not st.session_state.get('logged_in'):
        st.title("Login")
        login_form()
        return
    
    if not st.session_state.is_admin:
        st.header("User Panel")
        keys = c.execute('SELECT id, key, username, used_tokens, total_tokens FROM api_keys WHERE is_active = 1 and username = ?', (st.session_state.username, )).fetchall()
        for key in keys:
            with st.expander(f"Key {key[0]}"):
                st.write(f"Key: {key[1]}")
                st.write(f"User Name: {key[2]}")
                st.write(f"Tokens Used: {key[3]}")
                st.write(f"Tokens Total: {key[4]}")
                if st.button(f"Revoke Key {key[0]}"):
                    c.execute('UPDATE api_keys SET is_active = 0 WHERE id = ?', (key[0],))
                    conn.commit()
                    st.rerun()
        return

    st.header("Admin Panel")
    
    tab1, tab2, tab3 = st.tabs(["API Keys", "Users", "Blacklist"])
    
    with tab1:
        st.subheader("API Key Management")
        with st.form("Generate Key"):
            username = st.text_input("User Name")
            key = st.text_input("Api Key")
            token_total = st.number_input("Total tokens number")
            if st.form_submit_button("Generate Key"):
                api_key = generate_api_key(username, key, token_total)
                st.success(f"Generated API Key: {api_key}")
        
        st.subheader("Active Keys")
        keys = c.execute('SELECT id, key, username, used_tokens, total_tokens FROM api_keys WHERE is_active = 1').fetchall()
        for key in keys:
            with st.expander(f"Key {key[0]}" + " - " + f"{key[1]}" + " - " + f"{key[2]}"):
                st.write(f"Key: {key[1]}")
                st.write(f"User ID: {key[2]}")
                st.write(f"Tokens Used: {key[3]}")
                st.write(f"Tokens Total: {key[4]}")
                if st.button(f"Revoke Key {key[0]}"):
                    c.execute('UPDATE api_keys SET is_active = 0 WHERE id = ?', (key[0],))
                    conn.commit()
                    st.rerun()
    
    with tab2:
        st.subheader("User Management")
        register_form()
        users = c.execute('SELECT id, username, is_admin FROM users').fetchall()
        for user in users:
            cols = st.columns([2,1,2])
            cols[0].write(f"User {user[1]}")
            cols[1].checkbox("Admin", value=bool(user[2]), key=f"admin_{user[0]}",
                            on_change=update_admin_status, args=(user[0],))
            if cols[2].button(f"Delete {user[1]}", key=f"del_{user[0]}"):
                delete_user(user[0])
    
    with tab3:
        st.subheader("Blacklist Management")
        with st.form("Add to Blacklist"):
            username = st.text_input("Username")
            reason = st.text_input("Reason")
            if st.form_submit_button("Add"):
                try:
                    c.execute('INSERT INTO blacklist (username, reason) VALUES (?, ?)', 
                            (username, reason))
                    conn.commit()
                    st.success("User blacklisted")
                except sqlite3.IntegrityError:
                    st.error("User already in blacklist")
            if st.form_submit_button("Delete"):
                try:
                    c.execute('DELETE FROM blacklist where username = ?', 
                            (username, ))
                    conn.commit()
                    st.success("User blacklisted")
                except sqlite3.IntegrityError:
                    st.error("User already in blacklist")

        st.subheader("Blacklisted Users")
        blacklist = c.execute('SELECT username, reason FROM blacklist').fetchall()
        for entry in blacklist:
            st.write(f"{entry[0]} - {entry[1]}")

def generate_api_key(username, key, total):
    c.execute('INSERT INTO api_keys (key, username, total_tokens) VALUES (?, ?, ?)', (key, username, total))
    conn.commit()
    return key

def update_admin_status(username):
    is_admin = st.session_state[f"admin_{username}"]
    c.execute('UPDATE users SET is_admin = ? WHERE username = ?', (int(is_admin), username))
    conn.commit()

def delete_user(username):
    c.execute('DELETE FROM users WHERE username = ?', (username,))
    c.execute('DELETE FROM api_keys WHERE username = ?', (username,))
    conn.commit()
    st.rerun()

# 修改后的主功能模块
def handle_user_input():
    # 文件上传组件
    uploaded_files = st.file_uploader(
        "上传文本文件（支持多个）",
        type=["txt", "docx", "doc", 'pdf'],
        accept_multiple_files=True,
        key="file_uploader"
    )

    # 处理新上传的文件
    if uploaded_files:
        new_files = save_uploaded_files(uploaded_files)
        st.session_state.uploaded_files.extend(new_files)
        # 清空上传器缓存
        st.session_state['file_uploader'].clear()

    # 合并文件内容和用户输入
    user_content = []

    if user_input := st.chat_input("请问我任何事!"):
        user_content.append(user_input)

        if st.session_state.get('enable_search', False):
            try:
                if not search_key:
                    raise ValueError("未配置搜索API密钥")
                search_results = web_search(user_input, search_key)
                user_content.insert(0, search_results)  # 将搜索结果放在最前面
            except Exception as e:
                st.error(f"搜索失败: {str(e)}")

        user_content.append(search_results) 

        # 如果有上传文件则处理
        if st.session_state.uploaded_files:
            file_content = format_file_contents(st.session_state.uploaded_files)
            user_content.append("\n[上传文件内容]\n" + file_content)

            # 清空已上传文件（根据需求可选）
            st.session_state.uploaded_files = []

        full_content = "\n".join(user_content)
        if not st.session_state.get('valid_key'):
            st.error("请提供有效key，可联系Juntao - jjt627464892。")
            return
        adjusted_length = sum(
            2 if '\u4e00' <= c <= '\u9fff' else 1 
            for c in full_content  # 使用合并后的内容
        )
        keys = c.execute('SELECT id, key, username, used_tokens, total_tokens FROM api_keys WHERE key = ?', 
                        (st.session_state.used_key,)).fetchone()

        if keys[3] + adjusted_length >= keys[4]:
            st.error("额度已经用完，请联系管理员申请，可联系Juntao - jjt627464892。")
            return

        c.execute('UPDATE api_keys SET used_tokens = used_tokens + ? WHERE key = ?',
                 (adjusted_length, st.session_state.used_key))
        conn.commit()

        st.session_state.messages.append({"role": "user", "content": full_content})

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            stream = client.chat.completions.create(
                model="deepseek-r1",
                messages=st.session_state.messages,
                stream=True
            )

            thinking_content = process_thinking_phase(stream)
            response_content = process_response_phase(stream)

            st.session_state.messages.append(
                {"role": "assistant", "content": thinking_content + response_content}
            )

        # 自动保存会话
        save_session()
    

def process_thinking_phase(stream):
    """Process the thinking phase of the chat model"""
    thinking_content = ""
    thinking_length = 0
    with st.status("Thinking...", expanded=True) as status:
        think_placeholder = st.empty()

        for chunk in stream:
            content = chunk.choices[0].delta.reasoning_content or ""
            thinking_content += content
            thinking_length += len(content)
            adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in content)
            c.execute('UPDATE api_keys SET used_tokens = used_tokens + ' + str(adjusted_length) + ' WHERE key = ?',(st.session_state.used_key, ))
            conn.commit()
            if content == "":
                status.update(label="Thinking complete!", state="complete", expanded=False)
                break
            think_placeholder.markdown(format_reasoning_response(thinking_content))
            
    return thinking_content

def process_response_phase(stream):
    """Process the response phase of the chat model"""
    response_placeholder = st.empty()
    response_content = ""

    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        response_content += content
        adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in content)
        c.execute('UPDATE api_keys SET used_tokens = used_tokens + ' + str(adjusted_length) + ' WHERE key = ?',(st.session_state.used_key,))
        conn.commit()
        response_placeholder.markdown(response_content)

    return response_content

def main_interface():
    st.markdown("<div style='text-align: center;'><img src='data:image/png;base64,{}' width='250'></div>"
               .format(base64.b64encode(open("public/deep-seek.png", "rb").read()).decode()), 
               unsafe_allow_html=True)

    # 初始化上传文件列表
    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = []
    # 显示已上传文件列表
    # if st.session_state.uploaded_files:
    #     st.subheader("已上传文件")
    #     files_to_delete = []

    #     for idx, file in enumerate(st.session_state.uploaded_files):
    #         cols = st.columns([4, 1])
    #         cols[0].write(f"📄 {file['name']} ({file['size']/1024:.1f}KB)")
    #         if cols[1].button("×", key=f"del_file_{idx}"):
    #             files_to_delete.append(idx)

    #     # 处理删除操作
    #     if files_to_delete:
    #         st.session_state.uploaded_files = [
    #             f for idx, f in enumerate(st.session_state.uploaded_files)
    #             if idx not in files_to_delete
    #         ]
    #         st.rerun()
    
    with st.sidebar:
        
        if st.button("⚙️ - 设置"):
            st.session_state.show_admin = not st.session_state.get('show_admin', False)

        st.session_state.enable_search = st.checkbox(
            "🔍 启用联网搜索",
            value=st.session_state.get('enable_search', False),
            help="启用后将从互联网获取实时信息"
        )

        if st.session_state.get('valid_key'):
            # 获取用户名
            username = c.execute('SELECT username FROM api_keys WHERE key = ?', 
                               (st.session_state.used_key,)).fetchone()[0]

            # 新会话按钮
            if st.button("🆕 - 新会话"):
                # 生成新会话ID
                st.session_state.current_session_id = str(uuid.uuid4())
                # 重置消息记录（保留系统消息）
                system_messages = [msg for msg in st.session_state.messages if msg["role"] == "system"]
                st.session_state.messages = system_messages.copy()
                st.session_state.show_admin = False
                st.rerun()

            # 历史会话列表
            st.subheader("历史会话")
            histories = c.execute('''
                SELECT session_id, session_name, updated_at 
                FROM history 
                WHERE username = ? 
                ORDER BY updated_at DESC 
                LIMIT 10
            ''', (username,)).fetchall()

            for hist in histories:
                col1, col2 = st.columns([4, 1])
                with col1:
                    if st.button(f"🗨️ {hist[1]}", key=f"load_{hist[0]}"):
                        st.session_state.show_admin = False
                        load_session(hist[0])
                with col2:
                    if st.button("×", key=f"del_{hist[0]}"):
                        c.execute('DELETE FROM history WHERE session_id = ?', (hist[0],))
                        conn.commit()
                        st.rerun()
    if st.session_state.get('show_admin'):
        admin_panel()
    else:
        display_chat_history()
        handle_user_input()

# 初始化管理员账户
def setup_admin():
    c.execute('SELECT 1 FROM users WHERE username = ?', (admin_user,))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)',
                 (admin_user, hash_password(admin_pass)))
        conn.commit()

# 在main_interface()函数之前补充这些方法
def display_message(message):
    """Display a message in the chat interface"""
    role = "user" if message["role"] == "user" else "assistant"
    with st.chat_message(role):
        if role == "assistant":
            display_assistant_message(message["content"])
        else:
            st.markdown(message["content"])

def display_assistant_message(content):
    """Display assistant message with thinking content if present"""
    pattern = r"<THINKING>(.*?)</THINKING>"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        thinking_content = match.group(0)
        response_content = content.replace(thinking_content, "")
        thinking_content = format_reasoning_response(thinking_content)
        with st.expander("Thinking complete!"):
            st.markdown(thinking_content)
        st.markdown(response_content)
    else:
        st.markdown(content)

def format_reasoning_response(thinking_content):
    """Format the reasoning response for display"""
    return (
        thinking_content
        .replace("<THINKING>", "")
        .replace("</THINKING>", "")
    )

def display_chat_history():
    """Display all previous messages in the chat history."""
    for message in st.session_state["messages"]:
        if message["role"] != "system":  # Skip system messages
            display_message(message)

# 修改后的主函数
def main():
    setup_admin()

    # 初始化会话ID
    if 'current_session_id' not in st.session_state:
        st.session_state.current_session_id = str(uuid.uuid4())

    # API密钥验证逻辑
    if not st.session_state.get('valid_key'):
        api_key = st.chat_input("使用前，请先输入api-key，由网站管理员颁发。")
        if api_key:
            if not re.fullmatch(r'^[A-Za-z0-9]+$', api_key):
                st.error("无效的 API key, 请联系Juntao - jjt627464892。")
            else:
                c.execute('SELECT username FROM api_keys WHERE key = ? AND is_active = 1', (api_key,))
                if result := c.fetchone():
                    st.session_state.valid_key = True
                    st.session_state.used_key = api_key
                    st.session_state.username = result[0]
                    st.rerun()
                else:
                    st.error("无效的 API key, 请联系Juntao - jjt627464892。")
        
    main_interface()
    

if __name__ == "__main__":

    dirs = 'uploads/'
    admin_user = os.getenv("ADMIN_USERNAME") 
    admin_pass = os.getenv("ADMIN_PASSWORD") 
    api_key = os.getenv("CHAT_API_KEY") 
    search_key = os.getenv("SEARCH_API_KEY") 
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    if not os.path.exists(dirs):
        os.makedirs(dirs)

    if "messages" not in st.session_state:
        st.session_state["messages"] = [
            {"role": "system", "content": "你是一个AI助手，请回答用户提出的问题。同时，如果用户提供了搜索结果，请在回答中添加相应的引用。"}
        ]
        st.session_state.valid_key = False
    main()
