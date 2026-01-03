"""
SPECTRO - Music Player
by Kochanov Digitals
"""

import os, json, uuid, secrets, smtplib, ssl, random, string, hashlib, requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, session, Response, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.secret_key = 'spectro_secret_key_kochanov_2025'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# ============ НАСТРОЙКИ ============
JAMENDO_CLIENT_ID = 'b54a8e42'
YOOMONEY_DONATE_LINK = 'https://raw.githubusercontent.com/zalomeYT/killme/refs/heads/main/reason.txt'

DATA_DIR = 'spectro_data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
PLAYLISTS_DIR = os.path.join(DATA_DIR, 'playlists')
UPLOADS_DIR = os.path.join(DATA_DIR, 'uploads')
AVATARS_DIR = os.path.join(DATA_DIR, 'avatars')
COVERS_DIR = os.path.join(DATA_DIR, 'covers')
USER_TRACKS_FILE = os.path.join(DATA_DIR, 'user_tracks.json')
LIKES_FILE = os.path.join(DATA_DIR, 'likes.json')
COMMENTS_FILE = os.path.join(DATA_DIR, 'comments.json')
FOLLOWERS_FILE = os.path.join(DATA_DIR, 'followers.json')
NOTIFICATIONS_FILE = os.path.join(DATA_DIR, 'notifications.json')
HISTORY_FILE = os.path.join(DATA_DIR, 'history.json')
TOKENS_FILE = os.path.join(DATA_DIR, 'tokens.json')
BANS_FILE = os.path.join(DATA_DIR, 'bans.json')
VERIFICATION_FILE = os.path.join(DATA_DIR, 'verification.json')

SMTP_SERVER, SMTP_PORT = 'smtp.mail.ru', 465
SMTP_EMAIL = 'spectro.kd.2025@bk.ru'
SMTP_PASSWORD = '3GLfP2CpknOUclkpegGl'
ADMIN_USERNAMES = ['admin']

for d in [DATA_DIR, PLAYLISTS_DIR, UPLOADS_DIR, AVATARS_DIR, COVERS_DIR]:
    os.makedirs(d, exist_ok=True)

ALLOWED_AUDIO = {'mp3', 'wav', 'ogg', 'm4a'}
ALLOWED_IMAGE = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# ============ УТИЛИТЫ ============
def load_json(fp, default=None):
    try:
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f: return json.load(f)
    except: pass
    return default if default is not None else {}

def save_json(fp, data):
    with open(fp, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def allowed_file(fn, exts): return '.' in fn and fn.rsplit('.', 1)[1].lower() in exts

# ============ ПОЛЬЗОВАТЕЛИ ============
def load_users(): return load_json(USERS_FILE, {})
def save_users(u): save_json(USERS_FILE, u)
def load_tokens(): return load_json(TOKENS_FILE, {})
def save_tokens(t): save_json(TOKENS_FILE, t)
def hash_password(p): return generate_password_hash(p)
def verify_password(h, p): return check_password_hash(h, p) if h.startswith(('pbkdf2:', 'scrypt:')) else h == hashlib.sha256(p.encode()).hexdigest()
def is_admin(username): return username.lower() in ADMIN_USERNAMES

def get_user_playlists(uid): return load_json(os.path.join(PLAYLISTS_DIR, f'{uid}.json'), [])
def save_user_playlists(uid, p): save_json(os.path.join(PLAYLISTS_DIR, f'{uid}.json'), p)

# ============ ЛАЙКИ ============
def load_likes(): return load_json(LIKES_FILE, {})
def save_likes(l): save_json(LIKES_FILE, l)
def toggle_like(uid, tid):
    likes = load_likes()
    if uid not in likes: likes[uid] = []
    if tid in likes[uid]: likes[uid].remove(tid); save_likes(likes); return False
    likes[uid].append(tid); save_likes(likes); return True
def get_user_likes(uid): return load_likes().get(uid, [])
def is_liked(uid, tid): return tid in get_user_likes(uid)

# ============ ПОДПИСКИ ============
def load_followers(): return load_json(FOLLOWERS_FILE, {})
def save_followers(f): save_json(FOLLOWERS_FILE, f)
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
def load_notifications(): return load_json(NOTIFICATIONS_FILE, {})
def save_notifications(n): save_json(NOTIFICATIONS_FILE, n)
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
def load_comments(): return load_json(COMMENTS_FILE, {})
def save_comments(c): save_json(COMMENTS_FILE, c)
def add_comment(tid, uid, username, text):
    comments = load_comments()
    if tid not in comments: comments[tid] = []
    c = {'id': uuid.uuid4().hex[:12], 'user_id': uid, 'username': username, 'text': text, 'created': datetime.now().isoformat()}
    comments[tid].append(c); save_comments(comments); return c
def get_comments(tid): return load_comments().get(tid, [])
def delete_comment(tid, cid, uid, is_admin=False):
    comments = load_comments()
    if tid in comments:
        for i, c in enumerate(comments[tid]):
            if c['id'] == cid and (c['user_id'] == uid or is_admin):
                comments[tid].pop(i); save_comments(comments); return True
    return False

# ============ БАНЫ ============
def load_bans(): return load_json(BANS_FILE, {})
def save_bans(b): save_json(BANS_FILE, b)
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
def load_verification(): return load_json(VERIFICATION_FILE, {})
def save_verification(v): save_json(VERIFICATION_FILE, v)
def generate_code(): return ''.join(random.choices(string.digits, k=6))
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

# ============ ТРЕКИ ============
def load_user_tracks(): return load_json(USER_TRACKS_FILE, [])
def save_user_tracks(t): save_json(USER_TRACKS_FILE, t)
def add_user_track(uid, username, title, artist, genre, filename, is_original=True, cover=None):
    tracks = load_user_tracks()
    tid = f"user_{uuid.uuid4().hex[:12]}"
    t = {'id': tid, 'title': title, 'artist': artist, 'genre': genre, 'filename': filename, 'uploaded_by': uid, 'uploaded_by_name': username, 'uploaded_at': datetime.now().isoformat(), 'approved': False, 'plays': 0, 'is_original': is_original, 'allow_comments': is_original, 'custom_cover': cover}
    tracks.append(t); save_user_tracks(tracks)
    for fid in load_followers().get(uid, []): add_notification(fid, 'new_track', {'track_id': tid, 'title': title, 'artist_id': uid, 'artist_name': username})
    return t
def get_user_track(tid):
    for t in load_user_tracks():
        if t['id'] == tid: return t
    return None
def update_track_cover(tid, cover):
    tracks = load_user_tracks()
    for t in tracks:
        if t['id'] == tid: t['custom_cover'] = cover; save_user_tracks(tracks); return True
    return False
def approve_track(tid):
    tracks = load_user_tracks()
    for t in tracks:
        if t['id'] == tid: t['approved'] = True; save_user_tracks(tracks); return True
    return False
def delete_user_track(tid, uid=None, is_admin=False):
    tracks = load_user_tracks()
    for i, t in enumerate(tracks):
        if t['id'] == tid and (is_admin or t['uploaded_by'] == uid):
            try: os.remove(os.path.join(UPLOADS_DIR, t['filename']))
            except: pass
            if t.get('custom_cover'):
                try: os.remove(os.path.join(COVERS_DIR, t['custom_cover']))
                except: pass
            tracks.pop(i); save_user_tracks(tracks); return True
    return False
def increment_plays(tid):
    tracks = load_user_tracks()
    for t in tracks:
        if t['id'] == tid: t['plays'] = t.get('plays', 0) + 1; save_user_tracks(tracks); return t['plays']
    return 0
def get_approved_tracks(): return [t for t in load_user_tracks() if t.get('approved')]
def get_pending_tracks(): return [t for t in load_user_tracks() if not t.get('approved')]
def get_user_uploaded_tracks(uid): return [t for t in load_user_tracks() if t['uploaded_by'] == uid]

# ============ ИСТОРИЯ ============
def load_history(): return load_json(HISTORY_FILE, {})
def save_history(h): save_json(HISTORY_FILE, h)
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

# ============ ДЕКОРАТОРЫ ============
def get_current_user():
    if 'user_id' not in session: return None
    users = load_users()
    uid = session['user_id']
    if uid in users:
        u = users[uid].copy()
        u['id'] = uid
        u['is_admin'] = is_admin(u['username'])
        u['spectrons'] = get_followers_count(uid)
        return u
    return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user: return jsonify({'success': False, 'error': 'Требуется авторизация'}), 401
        if is_banned(user['id']): return jsonify({'success': False, 'error': 'Вы заблокированы'}), 403
        return f(user, *args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
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
.track-uploader{font-size:.75rem;color:var(--p);margin-top:5px}.track-plays{font-size:.7rem;color:rgba(255,255,255,.5)}
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
.upload-area{border:2px dashed rgba(255,0,255,.5);border-radius:15px;padding:40px;text-align:center;cursor:pointer}
.upload-area:hover{border-color:var(--s)}
.playlist-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,0,255,.3);border-radius:15px;padding:20px}
.playlist-cover{width:100%;aspect-ratio:1;background:linear-gradient(135deg,var(--p),#8b00ff);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:3rem;margin-bottom:12px}
.user-item{display:flex;justify-content:space-between;align-items:center;padding:12px;background:rgba(255,255,255,.05);border-radius:10px;margin-bottom:10px;flex-wrap:wrap;gap:10px}
.user-item.banned{background:rgba(255,0,0,.2)}
.no-results{text-align:center;padding:40px;color:rgba(255,255,255,.5);grid-column:1/-1}
.message{padding:10px 15px;border-radius:8px;margin-bottom:15px;text-align:center;display:none}
.message.error{display:block;background:rgba(255,0,0,.2);color:#f66}
.message.success{display:block;background:rgba(0,255,0,.2);color:#6f6}
@media(max-width:768px){h1{font-size:1.8rem}.player{padding:12px;gap:10px}.progress-container{width:100%;order:10}.track-page{flex-direction:column}.track-page-cover{width:100%;max-width:300px;margin:0 auto}}
</style>
</head>
<body>
<div class="container">
<div id="authPage" style="display:none">
<h1 style="text-align:center;margin:40px 0">SPECTRO</h1>
<p class="brand-sub" style="text-align:center;margin-bottom:30px">by Kochanov Digitals</p>
<div class="auth-container" id="loginForm">
<h2 class="auth-title">Вход</h2>
<div id="loginMessage" class="message"></div>
<div class="input-group"><label>Email или имя</label><input type="text" class="input-field" id="loginEmail" placeholder="Введите email или имя"></div>
<div class="input-group"><label>Пароль</label><input type="password" class="input-field" id="loginPassword" placeholder="Введите пароль"></div>
<div class="checkbox-group"><input type="checkbox" id="rememberMe" checked><label for="rememberMe">Запомнить</label></div>
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
<button class="btn btn-secondary btn-small" onclick="logout()">Выйти</button>
</div>
</div>
<div id="mainContent">
<div class="tabs" id="mainTabs">
<div class="tab active" data-tab="search">Поиск</div>
<div class="tab" data-tab="likes">❤️ Нравится</div>
<div class="tab" data-tab="playlists">Плейлисты</div>
<div class="tab" data-tab="community">Сообщество</div>
<div class="tab" data-tab="recommendations">Для вас</div>
</div>
<div id="searchTab"><div class="search-container"><input type="text" class="search-input" id="searchInput" placeholder="Поиск музыки..." onkeypress="if(event.key==='Enter')searchMusic()"><button class="btn" onclick="searchMusic()">Поиск</button></div><div class="results" id="results"><div class="no-results">Введите запрос</div></div></div>
<div id="likesTab" style="display:none"><h2 style="color:var(--s);margin-bottom:20px">❤️ Понравившиеся</h2><div class="results" id="likedTracks"><div class="no-results">Пока нет</div></div></div>
<div id="playlistsTab" style="display:none"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px"><h2 style="color:var(--s)">Плейлисты</h2><button class="btn" onclick="showCreatePlaylistModal()">+ Создать</button></div><div class="results" id="playlistsGrid"><div class="no-results">Нет плейлистов</div></div></div>
<div id="communityTab" style="display:none"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px"><h2 style="color:var(--s)">Сообщество</h2><button class="btn" onclick="showUploadModal()">Загрузить</button></div><div class="results" id="communityTracks"><div class="no-results">Пока нет треков</div></div></div>
<div id="recommendationsTab" style="display:none"><h2 style="color:var(--s);margin-bottom:20px">🎯 Для вас</h2><div class="results" id="recTracks"><div class="no-results">Слушайте музыку</div></div></div>
</div>
</div>
</div>
<div class="modal" id="trackModal"><div class="modal-content" style="max-width:800px"><div class="modal-header"><h3 class="modal-title">Трек</h3><button class="close-btn" onclick="closeModal('trackModal')">&times;</button></div><div id="trackPageContent"></div></div></div>
<div class="modal" id="profileModal"><div class="modal-content" style="max-width:700px"><div class="modal-header"><h3 class="modal-title">Профиль</h3><button class="close-btn" onclick="closeModal('profileModal')">&times;</button></div><div id="profileContent"></div></div></div>
<div class="modal" id="settingsModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">Настройки</h3><button class="close-btn" onclick="closeModal('settingsModal')">&times;</button></div><div id="settingsMessage" class="message"></div><h4 style="color:var(--s);margin-bottom:15px">Аватар</h4><div style="display:flex;align-items:center;gap:15px;margin-bottom:20px"><img id="settingsAvatar" src="" style="width:80px;height:80px;border-radius:50%;object-fit:cover"><input type="file" id="avatarInput" accept="image/*" style="display:none" onchange="uploadAvatar()"><button class="btn btn-secondary" onclick="document.getElementById('avatarInput').click()">Изменить</button></div><h4 style="color:var(--s);margin-bottom:15px">Безопасность</h4><div class="checkbox-group"><input type="checkbox" id="twoFactorEnabled" onchange="toggle2FA()"><label for="twoFactorEnabled">Двухэтапная аутентификация</label></div><div class="input-group"><label>Резервный email</label><input type="email" class="input-field" id="backupEmail" placeholder="backup@email.com"><button class="btn btn-secondary btn-small" style="margin-top:10px" onclick="saveBackupEmail()">Сохранить</button></div></div></div>
<div class="modal" id="notificationsModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">🔔 Уведомления</h3><button class="close-btn" onclick="closeModal('notificationsModal')">&times;</button></div><div id="notificationsList"></div></div></div>
<div class="modal" id="createPlaylistModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">Создать плейлист</h3><button class="close-btn" onclick="closeModal('createPlaylistModal')">&times;</button></div><div id="playlistMessage" class="message"></div><div class="input-group"><label>Название</label><input type="text" class="input-field" id="playlistName" placeholder="Мой плейлист"></div><div class="input-group"><label>Описание</label><input type="text" class="input-field" id="playlistDesc" placeholder="Описание"></div><button class="btn" style="width:100%" onclick="createPlaylist()">Создать</button></div></div>
<div class="modal" id="addToPlaylistModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">В плейлист</h3><button class="close-btn" onclick="closeModal('addToPlaylistModal')">&times;</button></div><div id="playlistsForAdd"></div></div></div>
<div class="modal" id="uploadModal"><div class="modal-content"><div class="modal-header"><h3 class="modal-title">Загрузить трек</h3><button class="close-btn" onclick="closeModal('uploadModal')">&times;</button></div><div id="uploadMessage" class="message"></div><div class="upload-area" id="uploadArea" onclick="document.getElementById('fileInput').click()"><p style="font-size:1.2rem;margin-bottom:10px">📁 Выберите файл</p><p style="color:rgba(255,255,255,.5)">MP3, WAV, OGG (до 50MB)</p></div><input type="file" id="fileInput" accept=".mp3,.wav,.ogg,.m4a" style="display:none" onchange="fileSelected()"><div id="uploadForm" style="display:none;margin-top:20px"><p id="selectedFileName" style="color:var(--s);margin-bottom:15px"></p><div class="input-group"><label>Название</label><input type="text" class="input-field" id="uploadTitle" placeholder="Название"></div><div class="input-group"><label>Исполнитель</label><input type="text" class="input-field" id="uploadArtist" placeholder="Исполнитель"></div><div class="input-group"><label>Жанр</label><input type="text" class="input-field" id="uploadGenre" placeholder="Жанр"></div><div class="input-group"><label>Обложка</label><input type="file" id="coverInput" accept="image/*" class="input-field"></div><div class="checkbox-group"><input type="checkbox" id="isOriginal" checked><label for="isOriginal">Моя музыка (разрешить комментарии)</label></div><button class="btn" style="width:100%" onclick="uploadTrack()">Загрузить</button></div></div></div>
<div class="modal" id="adminModal"><div class="modal-content" style="max-width:800px"><div class="modal-header"><h3 class="modal-title">Админ-панель</h3><button class="close-btn" onclick="closeModal('adminModal')">&times;</button></div><div class="tabs" id="adminTabs"><div class="tab active" data-tab="users">Пользователи</div><div class="tab" data-tab="moderation">Модерация</div><div class="tab" data-tab="alltracks">Все треки</div></div><div id="adminUsersTab"><div id="adminUserList"></div></div><div id="adminModerationTab" style="display:none"><div id="pendingTracks"></div></div><div id="adminAllTracksTab" style="display:none"><div id="allTracksList"></div></div></div></div>
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
const audio=document.getElementById('audioPlayer');let currentTrack=null,currentUser=null,isLooping=false,rememberToken=localStorage.getItem('rememberToken');
document.querySelectorAll('.tabs').forEach(tabs=>{tabs.addEventListener('click',e=>{if(e.target.classList.contains('tab')){tabs.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));e.target.classList.add('active');const tab=e.target.dataset.tab;if(tabs.id==='mainTabs')showMainTab(tab);else if(tabs.id==='adminTabs')showAdminTab(tab)}})});
function showMainTab(tab){['search','likes','playlists','community','recommendations'].forEach(t=>{const el=document.getElementById(t+'Tab');if(el)el.style.display=t===tab?'block':'none'});if(tab==='community')loadCommunityTracks();if(tab==='playlists')loadPlaylists();if(tab==='likes')loadLikedTracks();if(tab==='recommendations')loadRecommendations()}
function showAdminTab(tab){document.getElementById('adminUsersTab').style.display=tab==='users'?'block':'none';document.getElementById('adminModerationTab').style.display=tab==='moderation'?'block':'none';document.getElementById('adminAllTracksTab').style.display=tab==='alltracks'?'block':'none';if(tab==='moderation')loadPendingTracks();if(tab==='alltracks')loadAllTracks()}
document.addEventListener('DOMContentLoaded',checkAuth);
async function checkAuth(){try{const headers=rememberToken?{'X-Remember-Token':rememberToken}:{};const res=await fetch('/api/auth/check',{headers});const data=await res.json();if(data.authenticated){currentUser=data.user;if(data.newToken){rememberToken=data.newToken;localStorage.setItem('rememberToken',rememberToken)}showMainApp()}else showAuthPage()}catch(e){showAuthPage()}}
function showAuthPage(){document.getElementById('authPage').style.display='block';document.getElementById('mainApp').style.display='none'}
function showMainApp(){document.getElementById('authPage').style.display='none';document.getElementById('mainApp').style.display='block';let display=currentUser.username;if(currentUser.is_admin)display+='<span class="admin-badge">ADMIN</span>';document.getElementById('userDisplay').innerHTML=display;document.getElementById('adminBtn').style.display=currentUser.is_admin?'inline-block':'none';if(currentUser.avatar)document.getElementById('userAvatar').src='/avatars/'+currentUser.avatar;updateNotificationBadge()}
function showLogin(){document.getElementById('loginForm').style.display='block';document.getElementById('registerForm').style.display='none'}
function showRegister(){document.getElementById('loginForm').style.display='none';document.getElementById('registerForm').style.display='block'}
function goHome(){document.querySelector('#mainTabs .tab').click()}
function showMessage(id,text,type){const el=document.getElementById(id);el.textContent=text;el.className='message '+type}
function closeModal(id){document.getElementById(id).classList.remove('active')}
async function sendCode(){const email=document.getElementById('regEmail').value.trim();if(!email||!email.includes('@'))return showMessage('registerMessage','Введите email','error');showMessage('registerMessage','Отправка...','success');const res=await fetch('/api/auth/send-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});const data=await res.json();if(data.success){document.getElementById('verificationSection').style.display='block';showMessage('registerMessage','Код отправлен','success')}else showMessage('registerMessage',data.error,'error')}
async function register(){const username=document.getElementById('regUsername').value.trim();const email=document.getElementById('regEmail').value.trim();const password=document.getElementById('regPassword').value;const code=document.getElementById('verificationCode').value.trim();if(!username||!email||!password||!code)return showMessage('registerMessage','Заполните все поля','error');const verifyRes=await fetch('/api/auth/verify-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,code})});if(!(await verifyRes.json()).success)return showMessage('registerMessage','Неверный код','error');const res=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,email,password,remember:true})});const data=await res.json();if(data.success){currentUser=data.user;if(data.rememberToken){rememberToken=data.rememberToken;localStorage.setItem('rememberToken',rememberToken)}showMainApp()}else showMessage('registerMessage',data.error,'error')}
async function login(){const email=document.getElementById('loginEmail').value.trim();const password=document.getElementById('loginPassword').value;const remember=document.getElementById('rememberMe').checked;if(!email||!password)return showMessage('loginMessage','Заполните все поля','error');const res=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password,remember})});const data=await res.json();if(data.success){currentUser=data.user;if(data.rememberToken){rememberToken=data.rememberToken;localStorage.setItem('rememberToken',rememberToken)}showMainApp()}else showMessage('loginMessage',data.error,'error')}
async function logout(){await fetch('/api/auth/logout',{method:'POST',headers:rememberToken?{'X-Remember-Token':rememberToken}:{}});localStorage.removeItem('rememberToken');rememberToken=null;currentUser=null;showAuthPage()}
async function searchMusic(){const query=document.getElementById('searchInput').value.trim();if(!query)return;document.getElementById('results').innerHTML='<div class="no-results">Поиск...</div>';const res=await fetch('/api/search?q='+encodeURIComponent(query));const data=await res.json();if(data.error){document.getElementById('results').innerHTML='<div class="no-results">'+data.error+'</div>';return}renderTracks(data.tracks,'results')}
function renderTracks(tracks,containerId){const container=document.getElementById(containerId);if(!tracks||tracks.length===0){container.innerHTML='<div class="no-results">Ничего не найдено</div>';return}container.innerHTML=tracks.map(t=>{const cover=t.cover||t.custom_cover?(t.custom_cover?'/covers/'+t.custom_cover:t.cover):'https://via.placeholder.com/200/1a1a2e/ff00ff?text=♪';return`<div class="track-card"><button class="like-btn ${t.is_liked?'liked':''}" onclick="event.stopPropagation();toggleLike('${t.id}',this)">❤️</button><img class="track-cover" src="${cover}" onclick="openTrackPage('${t.id}')" onerror="this.src='https://via.placeholder.com/200/1a1a2e/ff00ff?text=♪'"><div class="track-title" onclick="playTrack('${t.id}')">${t.title||'Unknown'}</div><div class="track-artist">${t.artist||'Анонимный автор'}</div>${t.uploaded_by_name?'<div class="track-uploader" onclick="openUserProfile(\\''+t.uploaded_by+'\\')">👤 '+t.uploaded_by_name+'</div>':''}${t.plays!==undefined?'<div class="track-plays">▶️ '+t.plays+'</div>':''}</div>`}).join('')}
async function playTrack(id){const res=await fetch('/api/track/'+id);const data=await res.json();if(!data.track)return;const t=data.track;currentTrack=t;document.getElementById('player').classList.add('active');document.getElementById('playerCover').src=t.cover||t.custom_cover?(t.custom_cover?'/covers/'+t.custom_cover:t.cover):'https://via.placeholder.com/55/1a1a2e/ff00ff?text=♪';document.getElementById('playerTitle').textContent=t.title;document.getElementById('playerArtist').textContent=t.artist;document.getElementById('likePlayerBtn').classList.toggle('active',t.is_liked);audio.src='/api/stream/'+id;try{await audio.play();updatePlayIcon(true);document.getElementById('equalizer').classList.remove('paused')}catch(e){console.log('Play error:',e)}fetch('/api/track/'+id+'/play',{method:'POST'})}
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
async function openTrackPage(trackId){const res=await fetch('/api/track/'+trackId);const data=await res.json();if(!data.track)return;const t=data.track;const cover=t.cover||t.custom_cover?(t.custom_cover?'/covers/'+t.custom_cover:t.cover):'https://via.placeholder.com/300/1a1a2e/ff00ff?text=♪';let html=`<div class="track-page"><div class="track-page-cover"><img src="${cover}"></div><div class="track-page-info"><h2 class="track-page-title">${t.title}</h2><p class="track-page-artist">${t.artist}</p>${t.uploaded_by_name?'<p style="color:var(--p)">Загрузил: '+t.uploaded_by_name+'</p>':''}${t.plays!==undefined?'<p style="color:rgba(255,255,255,.5)">▶️ '+t.plays+' прослушиваний</p>':''}<div class="track-actions"><button class="btn" onclick="playTrack('${t.id}')">▶️ Играть</button><button class="btn btn-like ${t.is_liked?'liked':''}" onclick="toggleLike('${t.id}',this)">❤️ Нравится</button><button class="btn btn-secondary" onclick="showAddToPlaylist('${t.id}')">📁 В плейлист</button>${t.uploaded_by===currentUser?.id||currentUser?.is_admin?'<button class="btn btn-admin" onclick="deleteTrack(\\''+t.id+'\\')">🗑️ Удалить</button>':''}</div>${t.uploaded_by===currentUser?.id?'<div style="margin-top:15px"><label>Изменить обложку:</label><input type="file" accept="image/*" onchange="updateTrackCover(\\''+t.id+'\\',this)"></div>':''}</div></div>`;if(t.allow_comments){html+=`<div class="comments-section"><h3 style="color:var(--s);margin-bottom:15px">💬 Комментарии</h3><div id="commentsFor${t.id}"></div><div class="comment-input"><input type="text" class="input-field" id="commentText${t.id}" placeholder="Написать комментарий..."><button class="btn" onclick="addComment('${t.id}')">Отправить</button></div></div>`}document.getElementById('trackPageContent').innerHTML=html;document.getElementById('trackModal').classList.add('active');if(t.allow_comments)loadComments(t.id)}
function openCurrentTrackPage(){if(currentTrack)openTrackPage(currentTrack.id)}
async function loadComments(trackId){const res=await fetch('/api/comments/'+trackId);const data=await res.json();const container=document.getElementById('commentsFor'+trackId);if(!container)return;if(!data.comments||data.comments.length===0){container.innerHTML='<p style="color:rgba(255,255,255,.5)">Пока нет комментариев</p>';return}container.innerHTML=data.comments.map(c=>`<div class="comment"><div class="comment-header"><span class="comment-author">${c.username}</span><span class="comment-date">${new Date(c.created).toLocaleDateString()}</span></div><div class="comment-text">${c.text}</div>${c.user_id===currentUser?.id||currentUser?.is_admin?'<button class="btn btn-small btn-secondary" onclick="deleteComment(\\''+trackId+'\\',\\''+c.id+'\\')">Удалить</button>':''}</div>`).join('')}
async function addComment(trackId){const input=document.getElementById('commentText'+trackId);const text=input.value.trim();if(!text)return;await fetch('/api/comments/'+trackId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});input.value='';loadComments(trackId)}
async function deleteComment(trackId,commentId){await fetch('/api/comments/'+trackId+'/'+commentId,{method:'DELETE'});loadComments(trackId)}
async function updateTrackCover(trackId,input){const file=input.files[0];if(!file)return;const formData=new FormData();formData.append('cover',file);await fetch('/api/track/'+trackId+'/cover',{method:'POST',body:formData});openTrackPage(trackId)}
async function deleteTrack(trackId){if(!confirm('Удалить трек?'))return;await fetch('/api/track/'+trackId,{method:'DELETE'});closeModal('trackModal');loadCommunityTracks()}
function showCreatePlaylistModal(){document.getElementById('createPlaylistModal').classList.add('active')}
async function createPlaylist(){const name=document.getElementById('playlistName').value.trim();const desc=document.getElementById('playlistDesc').value.trim();if(!name)return showMessage('playlistMessage','Введите название','error');const res=await fetch('/api/playlists',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description:desc})});if((await res.json()).success){closeModal('createPlaylistModal');loadPlaylists()}}
async function loadPlaylists(){const res=await fetch('/api/playlists');const data=await res.json();const container=document.getElementById('playlistsGrid');if(!data.playlists||data.playlists.length===0){container.innerHTML='<div class="no-results">Нет плейлистов</div>';return}container.innerHTML=data.playlists.map(p=>`<div class="playlist-card"><div class="playlist-cover">🎵</div><div class="track-title">${p.name}</div><div class="track-artist">${p.tracks?.length||0} треков</div></div>`).join('')}
async function showAddToPlaylist(trackId){const res=await fetch('/api/playlists');const data=await res.json();const container=document.getElementById('playlistsForAdd');if(!data.playlists||data.playlists.length===0){container.innerHTML='<p>Нет плейлистов. <a href="#" onclick="showCreatePlaylistModal()">Создать</a></p>'}else{container.innerHTML=data.playlists.map(p=>`<div class="user-item" onclick="addToPlaylist('${p.id}','${trackId}')"><span>${p.name}</span><span>${p.tracks?.length||0} треков</span></div>`).join('')}document.getElementById('addToPlaylistModal').classList.add('active')}
async function addToPlaylist(playlistId,trackId){await fetch('/api/playlists/'+playlistId+'/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_id:trackId})});closeModal('addToPlaylistModal');alert('Добавлено!')}
async function loadCommunityTracks(){const res=await fetch('/api/user-tracks');const data=await res.json();renderTracks(data.tracks||[],'communityTracks')}
async function loadRecommendations(){document.getElementById('recTracks').innerHTML='<div class="no-results">Загрузка...</div>';const res=await fetch('/api/recommendations');const data=await res.json();renderTracks(data.tracks||[],'recTracks')}
function showUploadModal(){document.getElementById('uploadModal').classList.add('active')}
function fileSelected(){const file=document.getElementById('fileInput').files[0];if(file){document.getElementById('selectedFileName').textContent='📄 '+file.name;document.getElementById('uploadForm').style.display='block';document.getElementById('uploadArea').style.display='none'}}
async function uploadTrack(){const file=document.getElementById('fileInput').files[0];const title=document.getElementById('uploadTitle').value.trim();const artist=document.getElementById('uploadArtist').value.trim();const genre=document.getElementById('uploadGenre').value.trim();const isOriginal=document.getElementById('isOriginal').checked;const coverFile=document.getElementById('coverInput').files[0];if(!file||!title||!artist)return showMessage('uploadMessage','Заполните название и исполнителя','error');showMessage('uploadMessage','Загрузка...','success');const formData=new FormData();formData.append('file',file);formData.append('title',title);formData.append('artist',artist);formData.append('genre',genre);formData.append('is_original',isOriginal);if(coverFile)formData.append('cover',coverFile);const res=await fetch('/api/upload-track',{method:'POST',body:formData});const data=await res.json();if(data.success){showMessage('uploadMessage','Трек загружен!','success');setTimeout(()=>{closeModal('uploadModal');resetUploadForm()},2000)}else showMessage('uploadMessage',data.error,'error')}
function resetUploadForm(){document.getElementById('fileInput').value='';document.getElementById('uploadTitle').value='';document.getElementById('uploadArtist').value='';document.getElementById('uploadGenre').value='';document.getElementById('coverInput').value='';document.getElementById('uploadForm').style.display='none';document.getElementById('uploadArea').style.display='block'}
function showMyProfile(){openUserProfile(currentUser.id)}
async function openUserProfile(userId){if(!userId)return;const res=await fetch('/api/user/'+userId);const data=await res.json();if(!data.user)return;const u=data.user;const avatar=u.avatar?'/avatars/'+u.avatar:'https://via.placeholder.com/100/1a1a2e/ff00ff?text=U';const isMe=u.id===currentUser?.id;let html=`<div class="profile-header"><img class="profile-avatar" src="${avatar}"><div class="profile-info"><h2>${u.username} ${u.is_admin?'<span class="admin-badge">ADMIN</span>':''}</h2><div class="profile-stats"><div class="stat"><div class="stat-value">${u.spectrons||0}</div><div class="stat-label">спектронов</div></div><div class="stat"><div class="stat-value">${u.tracks_count||0}</div><div class="stat-label">треков</div></div></div></div></div><div style="margin-bottom:20px">${isMe?'<button class="btn btn-secondary" onclick="showSettings()">⚙️ Настройки</button>':`<button class="btn ${u.is_following?'btn-secondary':''}" onclick="toggleFollow('${u.id}',this)">${u.is_following?'✓ Подписан':'+ Подписаться'}</button>`}</div><h3 style="color:var(--s);margin-bottom:15px">Треки</h3><div class="results" id="userTracks${u.id}"></div>`;document.getElementById('profileContent').innerHTML=html;document.getElementById('profileModal').classList.add('active');const tracksRes=await fetch('/api/user/'+userId+'/tracks');const tracksData=await tracksRes.json();renderTracks(tracksData.tracks||[],'userTracks'+u.id)}
async function toggleFollow(userId,btn){const res=await fetch('/api/follow/'+userId,{method:'POST'});const data=await res.json();if(data.success){btn.textContent=data.following?'✓ Подписан':'+ Подписаться';btn.classList.toggle('btn-secondary',data.following)}}
function showSettings(){closeModal('profileModal');document.getElementById('settingsAvatar').src=currentUser.avatar?'/avatars/'+currentUser.avatar:'https://via.placeholder.com/80/1a1a2e/ff00ff?text=U';document.getElementById('twoFactorEnabled').checked=currentUser.two_factor_enabled||false;document.getElementById('backupEmail').value=currentUser.backup_email||'';document.getElementById('settingsModal').classList.add('active')}
async function uploadAvatar(){const file=document.getElementById('avatarInput').files[0];if(!file)return;const formData=new FormData();formData.append('avatar',file);const res=await fetch('/api/user/avatar',{method:'POST',body:formData});const data=await res.json();if(data.success){currentUser.avatar=data.avatar;document.getElementById('settingsAvatar').src='/avatars/'+data.avatar;document.getElementById('userAvatar').src='/avatars/'+data.avatar;showMessage('settingsMessage','Аватар обновлён','success')}}
async function toggle2FA(){const enabled=document.getElementById('twoFactorEnabled').checked;const res=await fetch('/api/user/2fa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});const data=await res.json();if(data.success){currentUser.two_factor_enabled=enabled;showMessage('settingsMessage',enabled?'2FA включена':'2FA выключена','success')}}
async function saveBackupEmail(){const email=document.getElementById('backupEmail').value.trim();const res=await fetch('/api/user/backup-email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});if((await res.json()).success){currentUser.backup_email=email;showMessage('settingsMessage','Сохранено','success')}}
async function showNotifications(){const res=await fetch('/api/notifications');const data=await res.json();const container=document.getElementById('notificationsList');if(!data.notifications||data.notifications.length===0){container.innerHTML='<p style="color:rgba(255,255,255,.5)">Нет уведомлений</p>'}else{container.innerHTML=data.notifications.map(n=>{let text='';if(n.type==='new_follower')text='👤 Новый подписчик';else if(n.type==='new_track')text=`🎵 ${n.data.artist_name} выложил "${n.data.title}"`;else text=n.type;return`<div class="notification-item ${n.read?'':'unread'}"><div>${text}</div><div class="notification-time">${new Date(n.created).toLocaleDateString()}</div></div>`}).join('')}document.getElementById('notificationsModal').classList.add('active');fetch('/api/notifications/read',{method:'POST'});updateNotificationBadge()}
async function updateNotificationBadge(){const res=await fetch('/api/notifications/unread');const data=await res.json();const badge=document.getElementById('notifBadge');if(data.count>0){badge.textContent=data.count;badge.style.display='inline'}else badge.style.display='none'}
function showAdminPanel(){document.getElementById('adminModal').classList.add('active');loadAdminUsers()}
async function loadAdminUsers(){const res=await fetch('/api/admin/users');const data=await res.json();document.getElementById('adminUserList').innerHTML=(data.users||[]).map(u=>`<div class="user-item ${u.is_banned?'banned':''}"><div><strong>${u.username}</strong> ${u.is_admin?'<span class="admin-badge">ADMIN</span>':''}<br><small>${u.email}</small>${u.is_banned?'<br><span style="color:#f44">🚫 БАН</span>':''}</div><div>${!u.is_banned?`<button class="btn btn-small btn-secondary" onclick="warnUser('${u.id}')">⚠️</button><button class="btn btn-small btn-admin" onclick="banUser('${u.id}')">🚫</button>`:`<button class="btn btn-small" onclick="unbanUser('${u.id}')">✅</button>`}</div></div>`).join('')}
async function warnUser(userId){const reason=prompt('Причина:');if(reason===null)return;await fetch('/api/admin/warn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,reason})});loadAdminUsers()}
async function banUser(userId){const reason=prompt('Причина:');if(reason===null)return;await fetch('/api/admin/ban',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,reason})});loadAdminUsers()}
async function unbanUser(userId){await fetch('/api/admin/unban',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId})});loadAdminUsers()}
async function loadPendingTracks(){const res=await fetch('/api/admin/pending-tracks');const data=await res.json();document.getElementById('pendingTracks').innerHTML=(data.tracks||[]).length===0?'<p>Нет треков на модерации</p>':data.tracks.map(t=>`<div class="user-item"><div><strong>${t.title}</strong> - ${t.artist}<br><small>От: ${t.uploaded_by_name}</small></div><div><button class="btn btn-small" onclick="approveTrack('${t.id}')">✅</button><button class="btn btn-small btn-admin" onclick="rejectTrack('${t.id}')">❌</button></div></div>`).join('')}
async function loadAllTracks(){const res=await fetch('/api/admin/all-tracks');const data=await res.json();document.getElementById('allTracksList').innerHTML=(data.tracks||[]).map(t=>`<div class="user-item"><div><strong>${t.title}</strong> - ${t.artist}<br><small>От: ${t.uploaded_by_name||'Jamendo'}</small></div><div><button class="btn btn-small btn-admin" onclick="adminDeleteTrack('${t.id}')">🗑️</button></div></div>`).join('')}
async function approveTrack(trackId){await fetch('/api/admin/approve-track',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_id:trackId})});loadPendingTracks()}
async function rejectTrack(trackId){if(!confirm('Удалить?'))return;await fetch('/api/admin/delete-track',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_id:trackId})});loadPendingTracks()}
async function adminDeleteTrack(trackId){if(!confirm('Удалить трек?'))return;await fetch('/api/track/'+trackId,{method:'DELETE'});loadAllTracks()}
</script></body></html>'''


# ============ API РОУТЫ ============
@app.route('/')
def index(): return Response(render_template_string(HTML_TEMPLATE), headers={'Cache-Control': 'no-cache'})

@app.route('/avatars/<filename>')
def serve_avatar(filename): return send_from_directory(AVATARS_DIR, filename)

@app.route('/covers/<filename>')
def serve_cover(filename): return send_from_directory(COVERS_DIR, filename)

@app.route('/api/auth/check')
def auth_check():
    token = request.headers.get('X-Remember-Token')
    if 'user_id' in session:
        users = load_users()
        uid = session['user_id']
        if uid in users:
            if is_banned(uid): return jsonify({'authenticated': False, 'banned': True})
            u = users[uid]
            return jsonify({'authenticated': True, 'user': {'id': uid, 'username': u['username'], 'is_admin': is_admin(u['username']), 'avatar': u.get('avatar'), 'two_factor_enabled': u.get('two_factor_enabled'), 'backup_email': u.get('backup_email')}})
    if token:
        tokens = load_tokens()
        if token in tokens:
            uid = tokens[token]['user_id']
            users = load_users()
            if uid in users:
                if is_banned(uid): return jsonify({'authenticated': False, 'banned': True})
                session['user_id'] = uid
                session.permanent = True
                new_token = secrets.token_urlsafe(32)
                del tokens[token]
                tokens[new_token] = {'user_id': uid, 'created': datetime.now().isoformat()}
                save_tokens(tokens)
                u = users[uid]
                return jsonify({'authenticated': True, 'user': {'id': uid, 'username': u['username'], 'is_admin': is_admin(u['username']), 'avatar': u.get('avatar')}, 'newToken': new_token})
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
    session['user_id'] = uid
    session.permanent = True
    resp = {'success': True, 'user': {'id': uid, 'username': username, 'is_admin': is_admin(username)}}
    if data.get('remember'):
        token = secrets.token_urlsafe(32)
        tokens = load_tokens()
        tokens[token] = {'user_id': uid, 'created': datetime.now().isoformat()}
        save_tokens(tokens)
        resp['rememberToken'] = token
    return jsonify(resp)

@app.route('/api/auth/login', methods=['POST'])
def login_route():
    data = request.get_json()
    login_id, password, remember = data.get('email', '').strip().lower(), data.get('password', ''), data.get('remember', False)
    users = load_users()
    for uid, u in users.items():
        if u.get('email', '').lower() == login_id or u['username'].lower() == login_id:
            if is_banned(uid): return jsonify({'success': False, 'error': 'Аккаунт заблокирован'})
            if verify_password(u['password'], password):
                session['user_id'] = uid
                session.permanent = True
                resp = {'success': True, 'user': {'id': uid, 'username': u['username'], 'is_admin': is_admin(u['username']), 'avatar': u.get('avatar')}}
                if remember:
                    token = secrets.token_urlsafe(32)
                    tokens = load_tokens()
                    tokens[token] = {'user_id': uid, 'created': datetime.now().isoformat()}
                    save_tokens(tokens)
                    resp['rememberToken'] = token
                return jsonify(resp)
            return jsonify({'success': False, 'error': 'Неверный пароль'})
    return jsonify({'success': False, 'error': 'Пользователь не найден'})

@app.route('/api/auth/logout', methods=['POST'])
def logout_route():
    token = request.headers.get('X-Remember-Token')
    if token:
        tokens = load_tokens()
        if token in tokens: del tokens[token]; save_tokens(tokens)
    session.pop('user_id', None)
    return jsonify({'success': True})

@app.route('/api/search')
def search_route():
    query = request.args.get('q', '')
    if not query: return jsonify({'error': 'Введите запрос', 'tracks': []})
    tracks = search_jamendo(query)
    uid = session.get('user_id')
    if uid:
        likes = get_user_likes(uid)
        for t in tracks: t['is_liked'] = t['id'] in likes
    return jsonify({'tracks': tracks})

@app.route('/api/track/<track_id>')
def get_track_route(track_id):
    uid = session.get('user_id')
    track = get_jamendo_track(track_id) if track_id.startswith('jam_') else get_user_track(track_id)
    if not track: return jsonify({'track': None})
    if uid: track['is_liked'] = is_liked(uid, track_id)
    return jsonify({'track': track})

@app.route('/api/track/<track_id>/play', methods=['POST'])
def track_play_route(track_id):
    uid = session.get('user_id')
    if track_id.startswith('user_'):
        increment_plays(track_id)
        track = get_user_track(track_id)
        if track and uid: update_history(uid, track)
    elif uid:
        track = get_jamendo_track(track_id)
        if track: update_history(uid, track)
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
    track = get_user_track(track_id)
    if not track: return jsonify({'error': 'Не найдено'}), 404
    if not track.get('approved'):
        user = get_current_user()
        if not user or (user['id'] != track['uploaded_by'] and not user.get('is_admin')): return jsonify({'error': 'На модерации'}), 403
    return send_from_directory(UPLOADS_DIR, track['filename'], mimetype='audio/mpeg')

@app.route('/api/track/<track_id>/cover', methods=['POST'])
@require_auth
def update_cover_route(user, track_id):
    track = get_user_track(track_id)
    if not track or track['uploaded_by'] != user['id']: return jsonify({'success': False})
    if 'cover' not in request.files: return jsonify({'success': False})
    file = request.files['cover']
    if not allowed_file(file.filename, ALLOWED_IMAGE): return jsonify({'success': False})
    filename = f"{track_id}_{secure_filename(file.filename)}"
    file.save(os.path.join(COVERS_DIR, filename))
    update_track_cover(track_id, filename)
    return jsonify({'success': True})

@app.route('/api/track/<track_id>', methods=['DELETE'])
@require_auth
def delete_track_route(user, track_id):
    return jsonify({'success': delete_user_track(track_id, user['id'], user.get('is_admin'))})

@app.route('/api/like/<track_id>', methods=['POST'])
@require_auth
def like_route(user, track_id): return jsonify({'success': True, 'liked': toggle_like(user['id'], track_id)})

@app.route('/api/likes')
@require_auth
def likes_route(user):
    tracks = []
    for tid in get_user_likes(user['id']):
        t = get_jamendo_track(tid) if tid.startswith('jam_') else get_user_track(tid)
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

@app.route('/api/user-tracks')
def user_tracks_route():
    tracks = get_approved_tracks()
    uid = session.get('user_id')
    if uid:
        likes = get_user_likes(uid)
        for t in tracks: t['is_liked'] = t['id'] in likes
    return jsonify({'tracks': tracks})

@app.route('/api/upload-track', methods=['POST'])
@require_auth
def upload_track_route(user):
    if 'file' not in request.files: return jsonify({'success': False, 'error': 'Файл не выбран'})
    file = request.files['file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_AUDIO): return jsonify({'success': False, 'error': 'Недопустимый формат'})
    title, artist, genre = request.form.get('title', '').strip(), request.form.get('artist', '').strip(), request.form.get('genre', '').strip()
    is_original = request.form.get('is_original', 'true').lower() == 'true'
    if not title or not artist: return jsonify({'success': False, 'error': 'Укажите название и исполнителя'})
    filename = f"{user['id']}_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
    file.save(os.path.join(UPLOADS_DIR, filename))
    cover_filename = None
    if 'cover' in request.files:
        cover = request.files['cover']
        if cover.filename and allowed_file(cover.filename, ALLOWED_IMAGE):
            cover_filename = f"cover_{uuid.uuid4().hex[:8]}_{secure_filename(cover.filename)}"
            cover.save(os.path.join(COVERS_DIR, cover_filename))
    track = add_user_track(user['id'], user['username'], title, artist, genre, filename, is_original, cover_filename)
    return jsonify({'success': True, 'track': track})

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
    current = get_current_user()
    return jsonify({'user': {'id': user_id, 'username': u['username'], 'avatar': u.get('avatar'), 'is_admin': is_admin(u['username']), 'spectrons': get_followers_count(user_id), 'tracks_count': len(get_user_uploaded_tracks(user_id)), 'is_following': is_following(current['id'], user_id) if current else False}})

@app.route('/api/user/<user_id>/tracks')
def user_tracks_profile_route(user_id):
    return jsonify({'tracks': [t for t in get_user_uploaded_tracks(user_id) if t.get('approved')]})

@app.route('/api/user/avatar', methods=['POST'])
@require_auth
def avatar_route(user):
    if 'avatar' not in request.files: return jsonify({'success': False})
    file = request.files['avatar']
    if not allowed_file(file.filename, ALLOWED_IMAGE): return jsonify({'success': False})
    filename = f"{user['id']}_{secure_filename(file.filename)}"
    file.save(os.path.join(AVATARS_DIR, filename))
    users = load_users()
    users[user['id']]['avatar'] = filename
    save_users(users)
    return jsonify({'success': True, 'avatar': filename})

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

@app.route('/api/admin/warn', methods=['POST'])
@require_admin
def admin_warn_route(user):
    data = request.get_json()
    result = warn_user(data.get('user_id'), data.get('reason', ''), user['id'])
    return jsonify({'success': True, **result})

@app.route('/api/admin/pending-tracks')
@require_admin
def admin_pending_route(user): return jsonify({'tracks': get_pending_tracks()})

@app.route('/api/admin/all-tracks')
@require_admin
def admin_all_tracks_route(user): return jsonify({'tracks': load_user_tracks()})

@app.route('/api/admin/approve-track', methods=['POST'])
@require_admin
def admin_approve_route(user): return jsonify({'success': approve_track(request.get_json().get('track_id'))})

@app.route('/api/admin/delete-track', methods=['POST'])
@require_admin
def admin_delete_route(user): return jsonify({'success': delete_user_track(request.get_json().get('track_id'), is_admin=True)})

@app.route('/api/popular')
def popular_route():
    tracks = get_jamendo_popular()
    uid = session.get('user_id')
    if uid:
        likes = get_user_likes(uid)
        for t in tracks: t['is_liked'] = t['id'] in likes
    return jsonify({'tracks': tracks})

if __name__ == '__main__':
    print("=" * 50)
    print("SPECTRO - Music Player")
    print("by Kochanov Digitals")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
