# auth_utils.py
import bcrypt
import streamlit as st
from db_utils import conn, c

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def is_blacklisted(username):
    c.execute('SELECT 1 FROM blacklist WHERE username = ?', (username,))
    return c.fetchone() is not None

def authenticate_user(username, password):
    c.execute('SELECT password_hash, is_admin FROM users WHERE username = ?', (username,))
    result = c.fetchone()
    if result and verify_password(password, result[0]):
        st.session_state.is_admin = bool(result[1])
        return True
    return False

def login_form():
    with st.form("Login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if is_blacklisted(username):
                st.error("用户名已被封禁")
                return
            elif authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("凭证错误")

def register_form():
    with st.form("Register"):
        username = st.text_input("新用户名")
        password = st.text_input("新密码", type="password")
        if st.form_submit_button("注册"):
            if is_blacklisted(username):
                st.error("用户名已被封禁")
                return
            try:
                c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                         (username, hash_password(password)))
                conn.commit()
                st.success("注册成功！请登录")
            except sqlite3.IntegrityError:
                st.error("用户名已存在")
