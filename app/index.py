"""
SPECTRO - Music Player (Vercel Edition)
by Kochanov Digitals
"""

import os, json, uuid, secrets, smtplib, ssl, random, string, hashlib, requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, Response, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# ============ НАСТРОЙКИ ============
JAMENDO_CLIENT_ID = 'b54a8e42'
YOOMONEY_DONATE_LINK = 'https://yoomoney.ru/to/4100118944378406/500'

SMTP_SERVER, SMTP_PORT = 'smtp.mail.ru', 465
SMTP_EMAIL = 'spectro.kd.2025@bk.ru'
SMTP_PASSWORD = '3GLfP2CpknOUclkpegGl'
ADMIN_USERNAMES = ['admin']

# JSONBin.io для хранения данных (бесплатно)
# Создайте аккаунт на jsonbin.io и получите API ключ
JSONBIN_API_KEY = '$2a$10$fEtn7j4T1pLi1L6RBsJfLeQzOyrw13pzrcjsOTAnhatawdTosJ.eK'  # Замените на свой ключ
JSONBIN_BINS = {
    'users': None,  # ID бина создастся автоматически
    'tokens': None,
    'likes': None,
    'followers': None,
    'notifications': None,
    'comments': None,
    'playlists': None,
    'history': None,
    'bans': None,
    'verification': None,
    'user_tracks': None
}

# Локальный кэш для ускорения (в памяти serverless функции)
_cache = {}

def jsonbin_read(bin_id):
    """Читает данные из JSONBin"""
    if not bin_id or not JSONBIN_API_KEY.startswith('$2a'):
        return {}
    try:
        r = requests.get(f'https://api.jsonbin.io/v3/b/{bin_id}/latest', 
                        headers={'X-Access-Key': JSONBIN_API_KEY}, timeout=5)
        if r.status_code == 200:
            return r.json().get('record', {})
    except:
        pass
    return {}

def jsonbin_write(bin_id, data):
    """Записывает данные в JSONBin"""
    if not bin_id or not JSONBIN_API_KEY.startswith('$2a'):
        return False
    try:
        r = requests.put(f'https://api.jsonbin.io/v3/b/{bin_id}',
                        json=data,
                        headers={'X-Access-Key': JSONBIN_API_KEY, 'Content-Type': 'application/json'},
                        timeout=5)
        return r.status_code == 200
    except:
        return False

def jsonbin_create(name, initial_data=None):
    """Создаёт новый бин"""
    if not JSONBIN_API_KEY.startswith('$2a'):
        return None
    try:
        r = requests.post('https://api.jsonbin.io/v3/b',
                         json=initial_data or {},
                         headers={'X-Access-Key': JSONBIN_API_KEY, 'Content-Type': 'application/json', 'X-Bin-Name': f'spectro_{name}'},
                         timeout=5)
        if r.status_code == 200:
            return r.json().get('metadata', {}).get('id')
    except:
        pass
    return None

# Простое in-memory хранилище (для демо без JSONBin)
_memory_storage = {
    'users': {},
    'tokens': {},
    'likes': {},
    'followers': {},
    'notifications': {},
    'comments': {},
    'playlists': {},
    'history': {},
    'bans': {},
    'verification': {},
    'user_tracks': []
}

def load_data(key, default=None):
    """Загружает данные"""
    return _memory_storage.get(key, default if default is not None else {})

def save_data(key, data):
    """Сохраняет данные"""
    _memory_storage[key] = data

# ============ УТИЛИТЫ ============
def hash_password(p): return generate_password_hash(p)
def verify_password(h, p): return check_password_hash(h, p) if h.startswith(('pbkdf2:', 'scrypt:')) else h == hashlib.sha256(p.encode()).hexdigest()
def is_admin(username): return username.lower() in ADMIN_USERNAMES
def generate_code(): return ''.join(random.choices(string.digits, k=6))

# ============ ПОЛЬЗОВАТЕЛИ ============
def load_users(): return load_data('users', {})
def save_users(u): save_data('users', u)
def load_tokens(): return load_data('tokens', {})
def save_tokens(t): save_data('tokens', t)

# ============ ЛАЙКИ ============
def load_likes(): return load_data('likes', {})
def save_likes(l): save_data('likes', l)
def toggle_like(uid, tid):
    likes = load_likes()
    if uid not in likes: likes[uid] = []
    if tid in likes[uid]: likes[uid].remove(tid); save_likes(likes); return False
    likes[uid].append(tid); save_likes(likes); return True
def get_user_likes(uid): return load_likes().get(uid, [])
def is_liked(uid, tid): return tid in get_user_likes(uid)

# ============ ПОДПИСКИ ============
def load_followers(): return load_data('followers', {})
def save_followers(f): save_data('followers', f)
def toggle_follow(fid, tid):
    if fid == tid: return False, 0
    followers = load_followers()
    if tid not in followers: followers[tid] = []
    if fid in followers[tid]: followers[tid].remove(fid); save_followers(followers); return False, len(followers[tid])
    followers[tid].append(fid); save_followers(followers)
    add_notification(tid, 'new_follower', {'follower_id': fid})
    return True, len(followers[tid])
def get_followers_count(uid): return len(load_followers().get(uid, []))
def is_following(fid, tid): return fid in load_followers().get(tid, [])

# ============ УВЕДОМЛЕНИЯ ============
def load_notifications(): return load_data('notifications', {})
def save_notifications(n): save_data('notifications', n)
def add_notification(uid, ntype, data):
    notifs = load_notifications()
    if uid not in notifs: notifs[uid] = []
    notifs[uid].insert(0, {'id': uuid.uuid4().hex[:12], 'type': ntype, 'data': data, 'read': False, 'created': datetime.now().isoformat()})
    notifs[uid] = notifs[uid][:50]
    save_notifications(notifs)
def get_notifications(uid): return load_notifications().get(uid, [])
def mark_notifications_read(uid):
    notifs = load_notifications()
    if uid in notifs:
        for n in notifs[uid]: n['read'] = True
        save_notifications(notifs)
def get_unread_count(uid): return sum(1 for n in get_notifications(uid) if not n.get('read'))

# ============ КОММЕНТАРИИ ============
def load_comments(): return load_data('comments', {})
def save_comments(c): save_data('comments', c)
def add_comment(tid, uid, username, text):
    comments = load_comments()
    if tid not in comments: comments[tid] = []
    c = {'id': uuid.uuid4().hex[:12], 'user_id': uid, 'username': username, 'text': text, 'created': datetime.now().isoformat()}
    comments[tid].append(c); save_comments(comments); return c
def get_comments(tid): return load_comments().get(tid, [])
def delete_comment(tid, cid, uid, is_admin_user=False):
    comments = load_comments()
    if tid in comments:
        for i, c in enumerate(comments[tid]):
            if c['id'] == cid and (c['user_id'] == uid or is_admin_user):
                comments[tid].pop(i); save_comments(comments); return True
    return False

# ============ БАНЫ ============
def load_bans(): return load_data('bans', {})
def save_bans(b): save_data('bans', b)
def ban_user(uid, reason='', hours=None, admin=None):
    bans = load_bans()
    bans[uid] = {'reason': reason, 'banned_at': datetime.now().isoformat(), 'banned_by': admin}
    if hours: bans[uid]['until'] = (datetime.now() + timedelta(hours=hours)).isoformat()
    else: bans[uid]['permanent'] = True
    save_bans(bans)
def unban_user(uid):
    bans = load_bans()
    if uid in bans: del bans[uid]; save_bans(bans); return True
    return False
def is_banned(uid):
    bans = load_bans()
    if uid in bans:
        b = bans[uid]
        if b.get('permanent'): return True
        if 'until' in b:
            if datetime.now() < datetime.fromisoformat(b['until']): return True
            del bans[uid]; save_bans(bans)
    return False
def warn_user(uid, reason='', admin=None):
    users = load_users()
    if uid not in users: return {'warned': False}
    if 'warnings' not in users[uid]: users[uid]['warnings'] = []
    users[uid]['warnings'].append({'reason': reason, 'warned_by': admin, 'warned_at': datetime.now().isoformat()})
    save_users(users)
    add_notification(uid, 'warning', {'reason': reason})
    return {'warned': True, 'warnings_count': len(users[uid]['warnings'])}

# ============ EMAIL ============
def load_verification(): return load_data('verification', {})
def save_verification(v): save_data('verification', v)
def send_email(email, code):
    if not SMTP_EMAIL: print(f"[DEV] Code for {email}: {code}"); return True
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = SMTP_EMAIL, email, 'Spectro - Код'
        msg.attach(MIMEText(f'<h1 style="color:#ff00ff;">Код: {code}</h1>', 'html'))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ssl.create_default_context()) as s:
            s.login(SMTP_EMAIL, SMTP_PASSWORD); s.send_message(msg)
        return True
    except Exception as e: print(f"Email error: {e}"); return False
def create_verification(email):
    codes = load_verification()
    code = generate_code()
    codes[email.lower()] = {'code': code, 'created': datetime.now().isoformat(), 'attempts': 0}
    save_verification(codes); send_email(email, code); return True
def verify_code(email, code):
    codes = load_verification()
    key = email.lower()
    if key not in codes: return {'success': False, 'error': 'Код не найден'}
    d = codes[key]
    if datetime.now() > datetime.fromisoformat(d['created']) + timedelta(minutes=10): del codes[key]; save_verification(codes); return {'success': False, 'error': 'Код истёк'}
    if d['attempts'] >= 5: del codes[key]; save_verification(codes); return {'success': False, 'error': 'Много попыток'}
    if d['code'] != code: d['attempts'] += 1; save_verification(codes); return {'success': False, 'error': 'Неверный код'}
    del codes[key]; save_verification(codes); return {'success': True}

# ============ ПЛЕЙЛИСТЫ ============
def load_playlists(): return load_data('playlists', {})
def save_playlists(p): save_data('playlists', p)
def get_user_playlists(uid):
    playlists = load_playlists()
    return playlists.get(uid, [])
def save_user_playlists(uid, p):
    playlists = load_playlists()
    playlists[uid] = p
    save_playlists(playlists)

# ============ ИСТОРИЯ ============
def load_history(): return load_data('history', {})
def save_history(h): save_data('history', h)
def update_history(uid, track):
    history = load_history()
    if uid not in history: history[uid] = {'genres': {}, 'artists': {}, 'tracks': []}
    h = history[uid]
    g = track.get('genre', 'unknown')
    if g: h['genres'][g] = h['genres'].get(g, 0) + 1
    a = track.get('artist', 'Unknown')
    h['artists'][a] = h['artists'].get(a, 0) + 1
    h['tracks'].insert(0, {'id': track.get('id'), 'title': track.get('title'), 'played_at': datetime.now().isoformat()})
    h['tracks'] = h['tracks'][:100]
    save_history(history)
def get_user_history(uid): return load_history().get(uid, {'genres': {}, 'artists': {}, 'tracks': []})

# ============ JAMENDO API ============
JAMENDO_API = 'https://api.jamendo.com/v3.0'
def search_jamendo(query, limit=20):
    try:
        r = requests.get(f"{JAMENDO_API}/tracks/", params={'client_id': JAMENDO_CLIENT_ID, 'format': 'json', 'limit': limit, 'search': query, 'imagesize': 300, 'audioformat': 'mp32'}, timeout=10)
        if r.status_code == 200:
            return [{'id': f"jam_{t['id']}", 'title': t.get('name', 'Unknown'), 'artist': 'Анонимный автор', 'cover': t.get('image', ''), 'audio_url': t.get('audio', ''), 'is_jamendo': True} for t in r.json().get('results', [])]
    except: pass
    return []

def get_jamendo_track(tid):
    try:
        rid = tid.replace('jam_', '')
        r = requests.get(f"{JAMENDO_API}/tracks/", params={'client_id': JAMENDO_CLIENT_ID, 'format': 'json', 'id': rid, 'audioformat': 'mp32', 'imagesize': 300}, timeout=10)
        if r.status_code == 200:
            res = r.json().get('results', [])
            if res:
                t = res[0]
                return {'id': f"jam_{t['id']}", 'title': t.get('name', 'Unknown'), 'artist': 'Анонимный автор', 'cover': t.get('image', ''), 'audio_url': t.get('audio', ''), 'is_jamendo': True}
    except: pass
    return None

def get_jamendo_popular(limit=20):
    try:
        r = requests.get(f"{JAMENDO_API}/tracks/", params={'client_id': JAMENDO_CLIENT_ID, 'format': 'json', 'limit': limit, 'order': 'popularity_total', 'imagesize': 300, 'audioformat': 'mp32'}, timeout=10)
        if r.status_code == 200:
            return [{'id': f"jam_{t['id']}", 'title': t.get('name', 'Unknown'), 'artist': 'Анонимный автор', 'cover': t.get('image', ''), 'audio_url': t.get('audio', ''), 'is_jamendo': True} for t in r.json().get('results', [])]
    except: pass
    return []

# ============ РЕКОМЕНДАЦИИ ============
def get_recommendations(uid, limit=20):
    history = get_user_history(uid)
    likes = get_user_likes(uid)
    genres = sorted(history.get('genres', {}).items(), key=lambda x: x[1], reverse=True)[:3]
    recs = []
    for genre, _ in genres:
        try:
            r = requests.get(f"{JAMENDO_API}/tracks/", params={'client_id': JAMENDO_CLIENT_ID, 'format': 'json', 'limit': 10, 'tags': genre, 'imagesize': 300, 'audioformat': 'mp32', 'order': 'popularity_month'}, timeout=10)
            if r.status_code == 200:
                for t in r.json().get('results', []):
                    tid = f"jam_{t['id']}"
                    if tid not in likes and tid not in [x['id'] for x in recs]:
                        recs.append({'id': tid, 'title': t.get('name', 'Unknown'), 'artist': 'Анонимный автор', 'cover': t.get('image', ''), 'is_jamendo': True})
        except: pass
    if len(recs) < limit:
        for t in get_jamendo_popular(limit - len(recs)):
            if t['id'] not in likes and t['id'] not in [x['id'] for x in recs]: recs.append(t)
    return recs[:limit]

# ============ АВТОРИЗАЦИЯ ЧЕРЕЗ ТОКЕНЫ ============
def get_user_from_token():
    """Получает пользователя из токена в cookie"""
    token = request.cookies.get('auth_token')
    if not token: return None
    tokens = load_tokens()
    if token not in tokens: return None
    uid = tokens[token].get('user_id')
    users = load_users()
    if uid not in users: return None
    if is_banned(uid): return None
    u = users[uid].copy()
    u['id'] = uid
    u['is_admin'] = is_admin(u['username'])
    u['spectrons'] = get_followers_count(uid)
    return u

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_user_from_token()
        if not user: return jsonify({'success': False, 'error': 'Требуется авторизация'}), 401
        return f(user, *args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_user_from_token()
        if not user: return jsonify({'success': False, 'error': 'Требуется авторизация'}), 401
        if not user.get('is_admin'): return jsonify({'success': False, 'error': 'Нет прав'}), 403
        return f(user, *args, **kwargs)
    return decorated


# ============ HTML ШАБЛОН ============
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Spectro</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Rajdhani:wght@400;500;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}:root{--p:#ff00ff;--s:#00ffff;--bg:#0a0a0f;--bg2:#1a1a2e}
body{min-height:100vh;background:linear-gradient(135deg,var(--bg),var(--bg2),var(--bg));font-family:'Rajdhani',sans-serif;color:#fff;overflow-x:hidden}
.container{max-width:1200px;margin:0 auto;padding:20px;padding-bottom:140px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:30px;flex-wrap:wrap;gap:15px}
h1{font-family:'Orbitron',sans-serif;font-size:2.5rem;background:linear-gradient(90deg,var(--p),var(--s),var(--p));background-size:200% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:shine 3s linear infinite;cursor:pointer}
@keyframes shine{to{background-position:200% center}}
.brand-sub{font-size:.8rem;color:rgba(255,255,255,.5)}
.user-panel{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.user-info{display:flex;align-items:center;gap:8px;color:var(--s);font-weight:600;cursor:pointer}
.user-avatar{width:35px;height:35px;border-radius:50%;object-fit:cover;border:2px solid var(--p)}
.admin-badge{background:linear-gradient(135deg,#f00,#f60);padding:3px 8px;border-radius:10px;font-size:.7rem}
.notif-badge{background:#f00;color:#fff;border-radius:50%;padding:2px 6px;font-size:.7rem;margin-left:5px}
.btn{padding:10px 20px;font-family:'Orbitron',sans-serif;font-size:.9rem;background:linear-gradient(135deg,var(--p),#8b00ff);border:none;border-radius:25px;color:#fff;cursor:pointer;transition:all .3s}
.btn:hover{background:linear-gradient(135deg,var(--s),#0f8);transform:scale(1.02)}
.btn-secondary{background:rgba(255,255,255,.1)}.btn-admin{background:linear-gradient(135deg,#f00,#f60)}
.btn-donate{background:linear-gradient(135deg,#ffd700,#ff8c00)}.btn-small{padding:5px 12px;font-size:.8rem}
.btn-like{background:transparent;border:2px solid var(--p)}.btn-like.liked{background:var(--p)}
.auth-container{max-width:400px;margin:100px auto;padding:40px;background:rgba(255,255,255,.03);border:1px solid rgba(255,0,255,.3);border-radius:20px}
.auth-title{font-family:'Orbitron',sans-serif;font-size:1.8rem;text-align:center;margin-bottom:30px;color:var(--s)}
.input-group{margin-bottom:20px}.input-group label{display:block;margin-bottom:8px;color:rgba(255,255,255,.7)}
.input-field{width:100%;padding:15px 20px;font-size:1rem;background:rgba(255,255,255,.05);border:2px solid rgba(255,0,255,.3);border-radius:10px;color:#fff;outline:none;font-family:'Rajdhani',sans-serif}
.input-field:focus{border-color:var(--s)}
.checkbox-group{display:flex;align-items:center;gap:10px;margin-bottom:20px}
.auth-switch{text-align:center;margin-top:20px;color:rgba(255,255,255,.5)}.auth-switch a{color:var(--p);cursor:pointer}
.tabs{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:12px 25px;background:rgba(255,255,255,.05);border:1px solid rgba(255,0,255,.2);border-radius:25px;color:rgba(255,255,255,.7);cursor:pointer;transition:all .3s}
.tab.active,.tab:hover{background:linear-gradient(135deg,var(--p),#8b00ff);color:#fff}
.search-container{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap}
.search-input{flex:1;min-width:200px;padding:15px 25px;font-size:1rem;background:rgba(255,255,255,.05);border:2px solid var(--p);border-radius:50px;color:#fff;outline:none}
.results{display:grid;gap:20px;padding:20px 0;grid-template-columns:repeat(auto-fill,minmax(180px,1fr))}
.track-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,0,255,.3);border-radius:15px;padding:15px;cursor:pointer;transition:all .3s;position:relative}
.track-card:hover{border-color:var(--s);transform:translateY(-3px)}
.track-cover{width:100%;aspect-ratio:1;border-radius:10px;object-fit:cover;margin-bottom:12px;background:rgba(255,0,255,.1)}
.track-title{font-size:1rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-artist{font-size:.85rem;color:var(--s);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.like-btn{position:absolute;top:10px;right:10px;background:rgba(0,0,0,.5);border:none;border-radius:50%;width:30px;height:30px;cursor:pointer;color:#fff;font-size:1rem}
.like-btn.liked{color:#f06}
.player{position:fixed;bottom:0;left:0;right:0;background:linear-gradient(180deg,rgba(10,10,15,.95),rgba(26,26,46,.98));border-top:2px solid var(--p);padding:15px 30px;display:none;align-items:center;gap:20px;z-index:100;flex-wrap:wrap}
.player.active{display:flex}
.player-cover{width:55px;height:55px;border-radius:8px;object-fit:cover;cursor:pointer}
.player-info{flex:1;min-width:150px}.player-title{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.player-artist{font-size:.85rem;color:var(--s)}
.player-controls{display:flex;align-items:center;gap:10px}
.play-btn{width:50px;height:50px;border-radius:50%;background:linear-gradient(135deg,var(--p),#8b00ff);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center}
.play-btn svg{fill:#fff;width:24px;height:24px}
.control-btn{background:rgba(255,255,255,.1);border:none;border-radius:50%;width:35px;height:35px;cursor:pointer;color:#fff;font-size:1rem}
.control-btn.active{background:var(--p)}
.progress-container{flex:2;display:flex;align-items:center;gap:10px;min-width:200px}
.progress-bar{flex:1;height:6px;background:rgba(255,255,255,.2);border-radius:3px;cursor:pointer}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--p),var(--s));border-radius:3px;width:0%}
.time{font-size:.85rem;color:rgba(255,255,255,.7);min-width:40px}
.equalizer{display:flex;gap:5px;align-items:flex-end;height:30px;margin-left:15px}
.eq-bar{width:4px;background:var(--s);border-radius:2px;animation:eq .5s ease infinite alternate}
.eq-bar:nth-child(1){animation-delay:0s}.eq-bar:nth-child(2){animation-delay:.1s}.eq-bar:nth-child(3){animation-delay:.2s}.eq-bar:nth-child(4){animation-delay:.3s}.eq-bar:nth-child(5){animation-delay:.4s}
@keyframes eq{from{height:5px}to{height:25px}}.equalizer.paused .eq-bar{animation:none;height:5px}
.modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.8);z-index:1000;align-items:center;justify-content:center;padding:20px;overflow-y:auto}
.modal.active{display:flex}
.modal-content{background:linear-gradient(135deg,var(--bg),var(--bg2));border:1px solid rgba(255,0,255,.5);border-radius:20px;padding:30px;max-width:600px;width:100%;max-height:90vh;overflow-y:auto}
.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.modal-title{font-family:'Orbitron',sans-serif;font-size:1.3rem;color:var(--s)}
.close-btn{background:none;border:none;cursor:pointer;font-size:1.5rem;color:rgba(255,255,255,.5)}
.profile-header{display:flex;gap:20px;align-items:center;margin-bottom:30px;flex-wrap:wrap}
.profile-avatar{width:100px;height:100px;border-radius:50%;object-fit:cover;border:3px solid var(--p)}
.profile-stats{display:flex;gap:20px;margin-top:10px}
.stat{text-align:center}.stat-value{font-size:1.5rem;font-weight:700;color:var(--p)}.stat-label{font-size:.8rem;color:rgba(255,255,255,.5)}
.track-page{display:flex;gap:30px;flex-wrap:wrap}
.track-page-cover{width:300px;max-width:100%}.track-page-cover img{width:100%;border-radius:15px}
.track-page-info{flex:1;min-width:250px}
.track-page-title{font-family:'Orbitron',sans-serif;font-size:2rem;margin-bottom:10px}
.track-page-artist{font-size:1.2rem;color:var(--s);margin-bottom:20px}
.track-actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.comments-section{margin-top:30px}
.comment{background:rgba(255,255,255,.05);border-radius:10px;padding:15px;margin-bottom:10px}
.comment-header{display:flex;justify-content:space-between;margin-bottom:8px}
.comment-author{color:var(--s);font-weight:600}.comment-date{font-size:.8rem;color:rgba(255,255,255,.5)}
.comment-text{color:rgba(255,255,255,.9)}
.comment-input{display:flex;gap:10px;margin-top:15px}.comment-input input{flex:1}
.notification-item{padding:15px;background:rgba(255,255,255,.05);border-radius:10px;margin-bottom:10px;border-left:3px solid var(--p)}
.notification-item.unread{background:rgba(255,0,255,.1)}
.notification-time{font-size:.8rem;color:rgba(255,255,255,.5)}
.playlist-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,0,255,.3);border-radius:15px;padding:20px}
.playlist-cover{width:100%;aspect-ratio:1;background:linear-gradient(135deg,var(--p),#8b00ff);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:3rem;margin-bottom:12px}
.user-item{display:flex;justify-content:space-between;align-items:center;padding:12px;background:rgba(255,255,255,.05);border-radius:10px;margin-bottom:10px;flex-wrap:wrap;gap:10px}
.user-item.banned{background:rgba(255,0,0,.2)}
.no-results{text-align:center;padding:40px;color:rgba(255,255,255,.5);grid-column:1/-1}
.message{padding:10px 15px;border-radius:8px;margin-bottom:15px;text-align:center;display:none}
.message.error{display:block;background:rgba(255,0,0,.2);color:#f66}
.message.success{display:block;background:rgba(0,255,0,.2);color:#6f6}
.warning-banner{background:linear-gradient(135deg,#f60,#f00);padding:15px;border-radius:10px;margin-bottom:20px;text-align:center}
@media(max-width:768px){h1{font-size:1.8rem}.player{padding:12px;gap:10px}.progress-container{width:100%;order:10}.track-page{flex-direction:column}.track-page-cover{width:100%;max-width:300px;margin:0 auto}}
</style>
</head>
<body>
<div class="container">
<div class="warning-banner">⚠️ Демо-версия на Vercel. Данные хранятся в памяти и сбрасываются при перезапуске. Для постоянного хранения подключите базу данных.</div>
<div id="authPage" style="display:none">
<h1 style="text-align:center;margin:40px 0">SPECTRO</h1>
<p class="brand-sub" style="text-align:center;margin-bottom:30px">by Kochanov Digitals</p>
<div class="auth-container" id="loginForm">
<h2 class="auth-title">Вход</h2>
<div id="loginMessage" class="message"></div>
<div class="input-group"><label>Email или имя</label><input type="text" class="input-field" id="loginEmail" placeholder="Введите email или имя"></div>
<div class="input-group"><label>Пароль</label><input type="password" class="input-field" id="loginPassword" placeholder="Введите пароль"></div>
<button class="btn" style="width:100%;padding:15px" onclick="login()">Войти</button>
<p class="auth-switch">Нет аккаунта? <a onclick="showRegister()">Регистрация</a></p>
</div>
<div class="auth-container" id="registerForm" style="display:none">
<h2 class="auth-title">Регистрация</h2>
<div id="registerMessage" class="message"></div>
<div class="input-group"><label>Имя пользователя</label><input type="text" class="input-field" id="regUsername" placeholder="Придумайте имя"></div>
<div class="input-group"><label>Email</label><input type="email" class="input-field" id="regEmail" placeholder="Введите email"></div>
<div class="input-group"><label>Пароль</label><input type="password" class="input-field" id="regPassword" placeholder="Придумайте пароль"></div>
<button class="btn" style="width:100%;padding:15px" onclick="sendCode()">Получить код</button>
<div id="verificationSection" style="display:none;margin-top:20px">
<div class="input-group"><label>Код подтверждения</label><input type="text" class="input-field" id="verificationCode" placeholder="6-значный код" maxlength="6"></div>
<button class="btn" style="width:100%;padding:15px" onclick="register()">Создать аккаунт</button>
</div>
<p class="auth-switch">Уже есть аккаунт? <a onclick="showLogin()">Войти</a></p>
</div>
</div>
<div id="mainApp" style="display:none">
<div class="header">
<div onclick="goHome()" style="cursor:pointer"><h1>SPECTRO</h1><p class="brand-sub">by Kochanov Digitals</p></div>
<div class="user-panel">
<a href="''' + YOOMONEY_DONATE_LINK + '''" target="_blank" class="btn btn-donate btn-small">💝 Пожертвовать</a>
<div class="user-info" onclick="showMyProfile()"><img class="user-avatar" id="userAvatar" src="https://via.placeholder.com/35/1a1a2e/ff00ff?text=U"><span id="userDisplay"></span><span class="notif-badge" id="notifBadge" style="display:none">0</span></div>
<button class="btn btn-admin btn-small" id="adminBtn" style="display:none" onclick="showAdminPanel()">Админ</button>
<button class="btn btn-secondary btn-small" onclick="showNotifications()">🔔</button>
<button class="btn btn-secondary btn-small" onclick="showSettings()">⚙️</button>
<button class="btn btn-secondary btn-small" onclick="logout()">Выйти</button>
</div>
</div>
<div id="mainContent">
<div class="tabs" id="mainTabs">
<div class="tab active" data-tab="search">Поиск</div>
<div class="tab" data-tab="likes">❤️ Нравится</div>
<div class="tab" data-tab="playlists">Плейлисты</div>
<div class="tab" data-tab="recommendations">Для вас</div>
</div>
<div id="searchTab"><div class="search-container"><input type="text" class="search-input" id="searchInput" placeholder="Поиск музыки..." onkeypress="if(event.key==='Enter')searchMusic()"><button class="btn" onclick="searchMusic()">Поиск</button></div><div class="results" id="results"><div class="no-results">Введите запрос для поиска музыки</div></div></div>
<div id="likesTab" style="display:none"><h2 style="color:var(--s);margin-bottom:20px">❤️ Понравившиеся</h2><div class="results" id="likedTracks"><div class="no-results">Пока нет понравившихся треков</div></div></div>
<div id="playlistsTab" style="display:none"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px"><h2 style="color:var(--s)">Плейлисты</h2><button class="btn" onclick="showCreatePlaylistModal()">+ Создать</button></div><div class="results" id="playlistsGrid"><div class="no-results">Нет плейлистов</div></div></div>
<div id="recommendationsTab" style="display:none"><h2 style="color:var(--s);margin-bottom:20px">🎯 Рекомендации для вас</h2><div class="results" id="recTracks"><div class="no-results">Слушайте музыку для получения рекомендаций</div></div></div>
</div>
</div>
</div>
<div class="modal" id="trackModal"><div class="modal-content" style="max-width:800px"><div class="modal-header"><h3 class="modal-title">Трек</h3><button class="close-btn" onclick="closeModal('trackModal')">&times;</button></div><div id="trackPageContent"></div></div></div>
<div class="modal" id="profileModal"><div class="modal-content" style="max-width:700px"><div class="modal-header"><h3 class="modal-title">Профиль</h3><button class="close-btn" onclick="closeModal('profileModal')">&times;</button></div><div id="profileContent"></div></div></div>
<div class="modal" id="settingsModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">Настройки</h3><button class="close-btn" onclick="closeModal('settingsModal')">&times;</button></div><div id="settingsMessage" class="message"></div><h4 style="color:var(--s);margin-bottom:15px">Безопасность</h4><div class="checkbox-group"><input type="checkbox" id="twoFactorEnabled" onchange="toggle2FA()"><label for="twoFactorEnabled">Двухэтапная аутентификация</label></div><div class="input-group"><label>Резервный email</label><input type="email" class="input-field" id="backupEmail" placeholder="backup@email.com"><button class="btn btn-secondary btn-small" style="margin-top:10px" onclick="saveBackupEmail()">Сохранить</button></div></div></div>
<div class="modal" id="notificationsModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">🔔 Уведомления</h3><button class="close-btn" onclick="closeModal('notificationsModal')">&times;</button></div><div id="notificationsList"></div></div></div>
<div class="modal" id="createPlaylistModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">Создать плейлист</h3><button class="close-btn" onclick="closeModal('createPlaylistModal')">&times;</button></div><div id="playlistMessage" class="message"></div><div class="input-group"><label>Название</label><input type="text" class="input-field" id="playlistName" placeholder="Мой плейлист"></div><div class="input-group"><label>Описание</label><input type="text" class="input-field" id="playlistDesc" placeholder="Описание"></div><button class="btn" style="width:100%" onclick="createPlaylist()">Создать</button></div></div>
<div class="modal" id="addToPlaylistModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">Добавить в плейлист</h3><button class="close-btn" onclick="closeModal('addToPlaylistModal')">&times;</button></div><div id="playlistsForAdd"></div></div></div>
<div class="modal" id="adminModal"><div class="modal-content" style="max-width:800px"><div class="modal-header"><h3 class="modal-title">Админ-панель</h3><button class="close-btn" onclick="closeModal('adminModal')">&times;</button></div><div class="tabs" id="adminTabs"><div class="tab active" data-tab="users">Пользователи</div></div><div id="adminUsersTab"><div id="adminUserList"></div></div></div></div>
<div class="player" id="player">
<img class="player-cover" id="playerCover" src="" onclick="openCurrentTrackPage()">
<div class="player-info"><div class="player-title" id="playerTitle">-</div><div class="player-artist" id="playerArtist">-</div></div>
<div class="player-controls"><button class="control-btn" id="loopBtn" onclick="toggleLoop()" title="Зациклить">🔁</button><button class="play-btn" onclick="togglePlay()"><svg id="playIcon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button><button class="control-btn" id="likePlayerBtn" onclick="toggleLikeCurrentTrack()">❤️</button></div>
<div class="progress-container"><span class="time" id="currentTime">0:00</span><div class="progress-bar" onclick="seek(event)"><div class="progress-fill" id="progressFill"></div></div><span class="time" id="duration">0:00</span></div>
<div class="equalizer" id="equalizer"><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div></div>
</div>
<audio id="audioPlayer"></audio>
'''

HTML_TEMPLATE += '''<script>
const audio=document.getElementById('audioPlayer');let currentTrack=null,currentUser=null,isLooping=false;
document.querySelectorAll('.tabs').forEach(tabs=>{tabs.addEventListener('click',e=>{if(e.target.classList.contains('tab')){tabs.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));e.target.classList.add('active');const tab=e.target.dataset.tab;if(tabs.id==='mainTabs')showMainTab(tab);else if(tabs.id==='adminTabs')showAdminTab(tab)}})});
function showMainTab(tab){['search','likes','playlists','recommendations'].forEach(t=>{const el=document.getElementById(t+'Tab');if(el)el.style.display=t===tab?'block':'none'});if(tab==='playlists')loadPlaylists();if(tab==='likes')loadLikedTracks();if(tab==='recommendations')loadRecommendations()}
function showAdminTab(tab){document.getElementById('adminUsersTab').style.display=tab==='users'?'block':'none'}
document.addEventListener('DOMContentLoaded',checkAuth);
async function checkAuth(){try{const res=await fetch('/api/auth/check');const data=await res.json();if(data.authenticated){currentUser=data.user;showMainApp()}else showAuthPage()}catch(e){showAuthPage()}}
function showAuthPage(){document.getElementById('authPage').style.display='block';document.getElementById('mainApp').style.display='none'}
function showMainApp(){document.getElementById('authPage').style.display='none';document.getElementById('mainApp').style.display='block';let display=currentUser.username;if(currentUser.is_admin)display+='<span class="admin-badge">ADMIN</span>';document.getElementById('userDisplay').innerHTML=display;document.getElementById('adminBtn').style.display=currentUser.is_admin?'inline-block':'none';updateNotificationBadge()}
function showLogin(){document.getElementById('loginForm').style.display='block';document.getElementById('registerForm').style.display='none'}
function showRegister(){document.getElementById('loginForm').style.display='none';document.getElementById('registerForm').style.display='block'}
function goHome(){document.querySelector('#mainTabs .tab').click()}
function showMessage(id,text,type){const el=document.getElementById(id);el.textContent=text;el.className='message '+type}
function closeModal(id){document.getElementById(id).classList.remove('active')}
async function sendCode(){const email=document.getElementById('regEmail').value.trim();if(!email||!email.includes('@'))return showMessage('registerMessage','Введите email','error');showMessage('registerMessage','Отправка...','success');const res=await fetch('/api/auth/send-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});const data=await res.json();if(data.success){document.getElementById('verificationSection').style.display='block';showMessage('registerMessage','Код отправлен на email','success')}else showMessage('registerMessage',data.error,'error')}
async function register(){const username=document.getElementById('regUsername').value.trim();const email=document.getElementById('regEmail').value.trim();const password=document.getElementById('regPassword').value;const code=document.getElementById('verificationCode').value.trim();if(!username||!email||!password||!code)return showMessage('registerMessage','Заполните все поля','error');const verifyRes=await fetch('/api/auth/verify-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,code})});if(!(await verifyRes.json()).success)return showMessage('registerMessage','Неверный код','error');const res=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,email,password})});const data=await res.json();if(data.success){currentUser=data.user;showMainApp()}else showMessage('registerMessage',data.error,'error')}
async function login(){const email=document.getElementById('loginEmail').value.trim();const password=document.getElementById('loginPassword').value;if(!email||!password)return showMessage('loginMessage','Заполните все поля','error');const res=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});const data=await res.json();if(data.success){currentUser=data.user;showMainApp()}else showMessage('loginMessage',data.error,'error')}
async function logout(){await fetch('/api/auth/logout',{method:'POST'});currentUser=null;showAuthPage()}
async function searchMusic(){const query=document.getElementById('searchInput').value.trim();if(!query)return;document.getElementById('results').innerHTML='<div class="no-results">Поиск...</div>';const res=await fetch('/api/search?q='+encodeURIComponent(query));const data=await res.json();if(data.error){document.getElementById('results').innerHTML='<div class="no-results">'+data.error+'</div>';return}renderTracks(data.tracks,'results')}
function renderTracks(tracks,containerId){const container=document.getElementById(containerId);if(!tracks||tracks.length===0){container.innerHTML='<div class="no-results">Ничего не найдено</div>';return}container.innerHTML=tracks.map(t=>{const cover=t.cover||'https://via.placeholder.com/200/1a1a2e/ff00ff?text=♪';return`<div class="track-card"><button class="like-btn ${t.is_liked?'liked':''}" onclick="event.stopPropagation();toggleLike('${t.id}',this)">❤️</button><img class="track-cover" src="${cover}" onclick="openTrackPage('${t.id}')" onerror="this.src='https://via.placeholder.com/200/1a1a2e/ff00ff?text=♪'"><div class="track-title" onclick="playTrack('${t.id}')">${t.title||'Unknown'}</div><div class="track-artist">${t.artist||'Анонимный автор'}</div></div>`}).join('')}
async function playTrack(id){const res=await fetch('/api/track/'+id);const data=await res.json();if(!data.track)return;const t=data.track;currentTrack=t;document.getElementById('player').classList.add('active');document.getElementById('playerCover').src=t.cover||'https://via.placeholder.com/55/1a1a2e/ff00ff?text=♪';document.getElementById('playerTitle').textContent=t.title;document.getElementById('playerArtist').textContent=t.artist;document.getElementById('likePlayerBtn').classList.toggle('active',t.is_liked);audio.src='/api/stream/'+id;try{await audio.play();updatePlayIcon(true);document.getElementById('equalizer').classList.remove('paused')}catch(e){console.log('Play error:',e)}fetch('/api/track/'+id+'/play',{method:'POST'})}
function togglePlay(){if(audio.paused){audio.play();updatePlayIcon(true);document.getElementById('equalizer').classList.remove('paused')}else{audio.pause();updatePlayIcon(false);document.getElementById('equalizer').classList.add('paused')}}
function updatePlayIcon(playing){document.getElementById('playIcon').innerHTML=playing?'<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>':'<path d="M8 5v14l11-7z"/>'}
function toggleLoop(){isLooping=!isLooping;audio.loop=isLooping;document.getElementById('loopBtn').classList.toggle('active',isLooping)}
audio.addEventListener('timeupdate',()=>{if(audio.duration){document.getElementById('progressFill').style.width=(audio.currentTime/audio.duration*100)+'%';document.getElementById('currentTime').textContent=formatTime(audio.currentTime)}});
audio.addEventListener('loadedmetadata',()=>{document.getElementById('duration').textContent=formatTime(audio.duration)});
audio.addEventListener('ended',()=>{updatePlayIcon(false);document.getElementById('equalizer').classList.add('paused')});
audio.addEventListener('pause',()=>{updatePlayIcon(false);document.getElementById('equalizer').classList.add('paused')});
audio.addEventListener('play',()=>{updatePlayIcon(true);document.getElementById('equalizer').classList.remove('paused')});
function seek(e){const rect=e.currentTarget.getBoundingClientRect();audio.currentTime=((e.clientX-rect.left)/rect.width)*audio.duration}
function formatTime(s){if(isNaN(s))return'0:00';const m=Math.floor(s/60),sec=Math.floor(s%60);return m+':'+(sec<10?'0':'')+sec}
async function toggleLike(trackId,btn){const res=await fetch('/api/like/'+trackId,{method:'POST'});const data=await res.json();if(data.success)btn.classList.toggle('liked',data.liked)}
async function toggleLikeCurrentTrack(){if(!currentTrack)return;const res=await fetch('/api/like/'+currentTrack.id,{method:'POST'});const data=await res.json();if(data.success)document.getElementById('likePlayerBtn').classList.toggle('active',data.liked)}
async function loadLikedTracks(){const res=await fetch('/api/likes');const data=await res.json();renderTracks(data.tracks||[],'likedTracks')}
async function openTrackPage(trackId){const res=await fetch('/api/track/'+trackId);const data=await res.json();if(!data.track)return;const t=data.track;const cover=t.cover||'https://via.placeholder.com/300/1a1a2e/ff00ff?text=♪';let html=`<div class="track-page"><div class="track-page-cover"><img src="${cover}"></div><div class="track-page-info"><h2 class="track-page-title">${t.title}</h2><p class="track-page-artist">${t.artist}</p><div class="track-actions"><button class="btn" onclick="playTrack('${t.id}')">▶️ Играть</button><button class="btn btn-like ${t.is_liked?'liked':''}" onclick="toggleLike('${t.id}',this)">❤️ Нравится</button><button class="btn btn-secondary" onclick="showAddToPlaylist('${t.id}')">📁 В плейлист</button></div></div></div>`;document.getElementById('trackPageContent').innerHTML=html;document.getElementById('trackModal').classList.add('active')}
function openCurrentTrackPage(){if(currentTrack)openTrackPage(currentTrack.id)}
function showCreatePlaylistModal(){document.getElementById('createPlaylistModal').classList.add('active')}
async function createPlaylist(){const name=document.getElementById('playlistName').value.trim();const desc=document.getElementById('playlistDesc').value.trim();if(!name)return showMessage('playlistMessage','Введите название','error');const res=await fetch('/api/playlists',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description:desc})});if((await res.json()).success){closeModal('createPlaylistModal');loadPlaylists()}}
async function loadPlaylists(){const res=await fetch('/api/playlists');const data=await res.json();const container=document.getElementById('playlistsGrid');if(!data.playlists||data.playlists.length===0){container.innerHTML='<div class="no-results">Нет плейлистов</div>';return}container.innerHTML=data.playlists.map(p=>`<div class="playlist-card"><div class="playlist-cover">🎵</div><div class="track-title">${p.name}</div><div class="track-artist">${p.tracks?.length||0} треков</div></div>`).join('')}
async function showAddToPlaylist(trackId){const res=await fetch('/api/playlists');const data=await res.json();const container=document.getElementById('playlistsForAdd');if(!data.playlists||data.playlists.length===0){container.innerHTML='<p>Нет плейлистов. <a href="#" onclick="showCreatePlaylistModal()">Создать</a></p>'}else{container.innerHTML=data.playlists.map(p=>`<div class="user-item" onclick="addToPlaylist('${p.id}','${trackId}')"><span>${p.name}</span><span>${p.tracks?.length||0} треков</span></div>`).join('')}document.getElementById('addToPlaylistModal').classList.add('active')}
async function addToPlaylist(playlistId,trackId){await fetch('/api/playlists/'+playlistId+'/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_id:trackId})});closeModal('addToPlaylistModal');alert('Добавлено!')}
async function loadRecommendations(){document.getElementById('recTracks').innerHTML='<div class="no-results">Загрузка...</div>';const res=await fetch('/api/recommendations');const data=await res.json();renderTracks(data.tracks||[],'recTracks')}
function showMyProfile(){openUserProfile(currentUser.id)}
async function openUserProfile(userId){if(!userId)return;const res=await fetch('/api/user/'+userId);const data=await res.json();if(!data.user)return;const u=data.user;const avatar='https://via.placeholder.com/100/1a1a2e/ff00ff?text=U';const isMe=u.id===currentUser?.id;let html=`<div class="profile-header"><img class="profile-avatar" src="${avatar}"><div class="profile-info"><h2>${u.username} ${u.is_admin?'<span class="admin-badge">ADMIN</span>':''}</h2><div class="profile-stats"><div class="stat"><div class="stat-value">${u.spectrons||0}</div><div class="stat-label">спектронов</div></div></div></div></div><div style="margin-bottom:20px">${!isMe?`<button class="btn ${u.is_following?'btn-secondary':''}" onclick="toggleFollow('${u.id}',this)">${u.is_following?'✓ Подписан':'+ Подписаться'}</button>`:''}</div>`;document.getElementById('profileContent').innerHTML=html;document.getElementById('profileModal').classList.add('active')}
async function toggleFollow(userId,btn){const res=await fetch('/api/follow/'+userId,{method:'POST'});const data=await res.json();if(data.success){btn.textContent=data.following?'✓ Подписан':'+ Подписаться';btn.classList.toggle('btn-secondary',data.following)}}
function showSettings(){document.getElementById('twoFactorEnabled').checked=currentUser.two_factor_enabled||false;document.getElementById('backupEmail').value=currentUser.backup_email||'';document.getElementById('settingsModal').classList.add('active')}
async function toggle2FA(){const enabled=document.getElementById('twoFactorEnabled').checked;const res=await fetch('/api/user/2fa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});const data=await res.json();if(data.success){currentUser.two_factor_enabled=enabled;showMessage('settingsMessage',enabled?'2FA включена':'2FA выключена','success')}}
async function saveBackupEmail(){const email=document.getElementById('backupEmail').value.trim();const res=await fetch('/api/user/backup-email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});if((await res.json()).success){currentUser.backup_email=email;showMessage('settingsMessage','Сохранено','success')}}
async function showNotifications(){const res=await fetch('/api/notifications');const data=await res.json();const container=document.getElementById('notificationsList');if(!data.notifications||data.notifications.length===0){container.innerHTML='<p style="color:rgba(255,255,255,.5)">Нет уведомлений</p>'}else{container.innerHTML=data.notifications.map(n=>{let text='';if(n.type==='new_follower')text='👤 Новый подписчик';else if(n.type==='new_track')text=`🎵 Новый трек`;else text=n.type;return`<div class="notification-item ${n.read?'':'unread'}"><div>${text}</div><div class="notification-time">${new Date(n.created).toLocaleDateString()}</div></div>`}).join('')}document.getElementById('notificationsModal').classList.add('active');fetch('/api/notifications/read',{method:'POST'});updateNotificationBadge()}
async function updateNotificationBadge(){const res=await fetch('/api/notifications/unread');const data=await res.json();const badge=document.getElementById('notifBadge');if(data.count>0){badge.textContent=data.count;badge.style.display='inline'}else badge.style.display='none'}
function showAdminPanel(){document.getElementById('adminModal').classList.add('active');loadAdminUsers()}
async function loadAdminUsers(){const res=await fetch('/api/admin/users');const data=await res.json();document.getElementById('adminUserList').innerHTML=(data.users||[]).map(u=>`<div class="user-item ${u.is_banned?'banned':''}"><div><strong>${u.username}</strong> ${u.is_admin?'<span class="admin-badge">ADMIN</span>':''}<br><small>${u.email}</small>${u.is_banned?'<br><span style="color:#f44">🚫 БАН</span>':''}</div><div>${!u.is_banned?`<button class="btn btn-small btn-admin" onclick="banUser('${u.id}')">🚫</button>`:`<button class="btn btn-small" onclick="unbanUser('${u.id}')">✅</button>`}</div></div>`).join('')}
async function banUser(userId){const reason=prompt('Причина:');if(reason===null)return;await fetch('/api/admin/ban',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,reason})});loadAdminUsers()}
async function unbanUser(userId){await fetch('/api/admin/unban',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId})});loadAdminUsers()}
</script></body></html>'''


# ============ API РОУТЫ ============
@app.route('/')
def index(): return Response(render_template_string(HTML_TEMPLATE), headers={'Cache-Control': 'no-cache'})

@app.route('/api/auth/check')
def auth_check():
    user = get_user_from_token()
    if user:
        return jsonify({'authenticated': True, 'user': {'id': user['id'], 'username': user['username'], 'is_admin': user.get('is_admin'), 'two_factor_enabled': user.get('two_factor_enabled'), 'backup_email': user.get('backup_email')}})
    return jsonify({'authenticated': False})

@app.route('/api/auth/send-code', methods=['POST'])
def send_code_route():
    email = request.get_json().get('email', '').strip().lower()
    if not email or '@' not in email: return jsonify({'success': False, 'error': 'Некорректный email'})
    create_verification(email)
    return jsonify({'success': True})

@app.route('/api/auth/verify-code', methods=['POST'])
def verify_code_route():
    data = request.get_json()
    return jsonify(verify_code(data.get('email', ''), data.get('code', '')))

@app.route('/api/auth/register', methods=['POST'])
def register_route():
    data = request.get_json()
    username, email, password = data.get('username', '').strip(), data.get('email', '').strip().lower(), data.get('password', '')
    if not username or not password or not email: return jsonify({'success': False, 'error': 'Заполните все поля'})
    if len(username) < 3: return jsonify({'success': False, 'error': 'Имя минимум 3 символа'})
    users = load_users()
    for uid, u in users.items():
        if u['username'].lower() == username.lower(): return jsonify({'success': False, 'error': 'Имя занято'})
        if u.get('email', '').lower() == email: return jsonify({'success': False, 'error': 'Email занят'})
    uid = str(uuid.uuid4())
    users[uid] = {'username': username, 'email': email, 'password': hash_password(password), 'created': datetime.now().isoformat()}
    save_users(users)
    token = secrets.token_urlsafe(32)
    tokens = load_tokens()
    tokens[token] = {'user_id': uid, 'created': datetime.now().isoformat()}
    save_tokens(tokens)
    resp = make_response(jsonify({'success': True, 'user': {'id': uid, 'username': username, 'is_admin': is_admin(username)}}))
    resp.set_cookie('auth_token', token, max_age=30*24*60*60, httponly=True, samesite='Lax')
    return resp

@app.route('/api/auth/login', methods=['POST'])
def login_route():
    data = request.get_json()
    login_id, password = data.get('email', '').strip().lower(), data.get('password', '')
    users = load_users()
    for uid, u in users.items():
        if u.get('email', '').lower() == login_id or u['username'].lower() == login_id:
            if is_banned(uid): return jsonify({'success': False, 'error': 'Аккаунт заблокирован'})
            if verify_password(u['password'], password):
                token = secrets.token_urlsafe(32)
                tokens = load_tokens()
                tokens[token] = {'user_id': uid, 'created': datetime.now().isoformat()}
                save_tokens(tokens)
                resp = make_response(jsonify({'success': True, 'user': {'id': uid, 'username': u['username'], 'is_admin': is_admin(u['username'])}}))
                resp.set_cookie('auth_token', token, max_age=30*24*60*60, httponly=True, samesite='Lax')
                return resp
            return jsonify({'success': False, 'error': 'Неверный пароль'})
    return jsonify({'success': False, 'error': 'Пользователь не найден'})

@app.route('/api/auth/logout', methods=['POST'])
def logout_route():
    token = request.cookies.get('auth_token')
    if token:
        tokens = load_tokens()
        if token in tokens: del tokens[token]; save_tokens(tokens)
    resp = make_response(jsonify({'success': True}))
    resp.delete_cookie('auth_token')
    return resp

@app.route('/api/search')
def search_route():
    query = request.args.get('q', '')
    if not query: return jsonify({'error': 'Введите запрос', 'tracks': []})
    tracks = search_jamendo(query)
    user = get_user_from_token()
    if user:
        likes = get_user_likes(user['id'])
        for t in tracks: t['is_liked'] = t['id'] in likes
    return jsonify({'tracks': tracks})

@app.route('/api/track/<track_id>')
def get_track_route(track_id):
    user = get_user_from_token()
    track = get_jamendo_track(track_id) if track_id.startswith('jam_') else None
    if not track: return jsonify({'track': None})
    if user: track['is_liked'] = is_liked(user['id'], track_id)
    return jsonify({'track': track})

@app.route('/api/track/<track_id>/play', methods=['POST'])
def track_play_route(track_id):
    user = get_user_from_token()
    if user:
        track = get_jamendo_track(track_id)
        if track: update_history(user['id'], track)
    return jsonify({'success': True})

@app.route('/api/stream/<track_id>')
def stream_route(track_id):
    if track_id.startswith('jam_'):
        track = get_jamendo_track(track_id)
        if track and track.get('audio_url'):
            try:
                r = requests.get(track['audio_url'], stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
                return Response(r.iter_content(8192), mimetype='audio/mpeg')
            except: pass
    return jsonify({'error': 'Не найдено'}), 404

@app.route('/api/like/<track_id>', methods=['POST'])
@require_auth
def like_route(user, track_id): return jsonify({'success': True, 'liked': toggle_like(user['id'], track_id)})

@app.route('/api/likes')
@require_auth
def likes_route(user):
    tracks = []
    for tid in get_user_likes(user['id']):
        t = get_jamendo_track(tid) if tid.startswith('jam_') else None
        if t: t['is_liked'] = True; tracks.append(t)
    return jsonify({'tracks': tracks})

@app.route('/api/comments/<track_id>')
def comments_route(track_id): return jsonify({'comments': get_comments(track_id)})

@app.route('/api/comments/<track_id>', methods=['POST'])
@require_auth
def add_comment_route(user, track_id):
    text = request.get_json().get('text', '').strip()
    if not text: return jsonify({'success': False})
    return jsonify({'success': True, 'comment': add_comment(track_id, user['id'], user['username'], text)})

@app.route('/api/comments/<track_id>/<comment_id>', methods=['DELETE'])
@require_auth
def delete_comment_route(user, track_id, comment_id):
    return jsonify({'success': delete_comment(track_id, comment_id, user['id'], user.get('is_admin'))})

@app.route('/api/playlists')
@require_auth
def playlists_route(user): return jsonify({'playlists': get_user_playlists(user['id'])})

@app.route('/api/playlists', methods=['POST'])
@require_auth
def create_playlist_route(user):
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name: return jsonify({'success': False})
    playlists = get_user_playlists(user['id'])
    playlists.append({'id': uuid.uuid4().hex[:12], 'name': name, 'description': data.get('description', ''), 'tracks': [], 'created': datetime.now().isoformat()})
    save_user_playlists(user['id'], playlists)
    return jsonify({'success': True})

@app.route('/api/playlists/<playlist_id>/add', methods=['POST'])
@require_auth
def add_to_playlist_route(user, playlist_id):
    track_id = request.get_json().get('track_id')
    playlists = get_user_playlists(user['id'])
    for p in playlists:
        if p['id'] == playlist_id:
            if track_id not in p['tracks']: p['tracks'].append(track_id); save_user_playlists(user['id'], playlists)
            return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/recommendations')
@require_auth
def recommendations_route(user):
    tracks = get_recommendations(user['id'])
    likes = get_user_likes(user['id'])
    for t in tracks: t['is_liked'] = t['id'] in likes
    return jsonify({'tracks': tracks})

@app.route('/api/user/<user_id>')
def user_profile_route(user_id):
    users = load_users()
    if user_id not in users: return jsonify({'user': None})
    u = users[user_id]
    current = get_user_from_token()
    return jsonify({'user': {'id': user_id, 'username': u['username'], 'is_admin': is_admin(u['username']), 'spectrons': get_followers_count(user_id), 'is_following': is_following(current['id'], user_id) if current else False}})

@app.route('/api/user/2fa', methods=['POST'])
@require_auth
def twofa_route(user):
    users = load_users()
    users[user['id']]['two_factor_enabled'] = request.get_json().get('enabled', False)
    save_users(users)
    return jsonify({'success': True})

@app.route('/api/user/backup-email', methods=['POST'])
@require_auth
def backup_email_route(user):
    users = load_users()
    users[user['id']]['backup_email'] = request.get_json().get('email', '')
    save_users(users)
    return jsonify({'success': True})

@app.route('/api/follow/<target_id>', methods=['POST'])
@require_auth
def follow_route(user, target_id):
    following, count = toggle_follow(user['id'], target_id)
    return jsonify({'success': True, 'following': following, 'spectrons': count})

@app.route('/api/notifications')
@require_auth
def notifications_route(user): return jsonify({'notifications': get_notifications(user['id'])})

@app.route('/api/notifications/unread')
@require_auth
def unread_route(user): return jsonify({'count': get_unread_count(user['id'])})

@app.route('/api/notifications/read', methods=['POST'])
@require_auth
def mark_read_route(user): mark_notifications_read(user['id']); return jsonify({'success': True})

@app.route('/api/admin/users')
@require_admin
def admin_users_route(user):
    users = load_users()
    return jsonify({'users': [{'id': uid, 'username': u['username'], 'email': u.get('email', ''), 'is_admin': is_admin(u['username']), 'is_banned': is_banned(uid)} for uid, u in users.items()]})

@app.route('/api/admin/ban', methods=['POST'])
@require_admin
def admin_ban_route(user):
    data = request.get_json()
    ban_user(data.get('user_id'), data.get('reason', ''), data.get('duration_hours'), user['id'])
    return jsonify({'success': True})

@app.route('/api/admin/unban', methods=['POST'])
@require_admin
def admin_unban_route(user): return jsonify({'success': unban_user(request.get_json().get('user_id'))})

@app.route('/api/popular')
def popular_route():
    tracks = get_jamendo_popular()
    user = get_user_from_token()
    if user:
        likes = get_user_likes(user['id'])
        for t in tracks: t['is_liked'] = t['id'] in likes
    return jsonify({'tracks': tracks})

# Vercel handler
app_handler = app
