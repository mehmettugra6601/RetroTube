from flask import Flask, request, render_template_string, Response, stream_with_context
import yt_dlp
import requests

app = Flask(__name__)

BASE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <title>Retro YT Proxy</title>
    <style>
        body { font-family: sans-serif; background: #e6e6e6; margin: 0; padding: 5px; font-size: 12px; }
        .header { background: #cc0000; color: #fff; padding: 6px; text-align: center; font-weight: bold; margin-bottom: 8px; }
        .search-box { background: #fff; padding: 8px; border: 1px solid #ccc; margin-bottom: 8px; text-align: center; }
        input[type="text"] { width: 60%; padding: 4px; }
        input[type="submit"] { padding: 4px 8px; background: #333; color: #fff; border: none; font-weight: bold; }
        .video-item { background: #fff; padding: 6px; border: 1px solid #ccc; margin-bottom: 6px; overflow: hidden; }
        .video-item img { float: left; margin-right: 8px; width: 80px; height: 60px; }
        .video-item a { color: #003399; text-decoration: none; font-weight: bold; display: block; }
        .btn-back { display: inline-block; background: #555; color: #fff; padding: 4px 8px; text-decoration: none; margin-bottom: 8px; font-size: 11px; }
        .play-btn { display: block; background: #28a745; color: #fff; padding: 12px; text-decoration: none; font-weight: bold; font-size: 13px; border-radius: 4px; text-align: center; margin: 8px 0; }
        .dl-btn { display: block; background: #6c757d; color: #fff; padding: 10px; text-decoration: none; font-weight: bold; font-size: 12px; border-radius: 4px; text-align: center; margin-top: 6px; }
        .quality-box { margin: 10px 0; padding: 6px; background: #f8f9fa; border: 1px solid #ddd; }
        .q-btn { display: inline-block; padding: 4px 8px; text-decoration: none; font-size: 11px; margin: 2px; border-radius: 3px; }
        .clear { clear: both; }
    </style>
</head>
<body>
    <div class="header">Retro YT Proxy</div>
    {% block content %}{% endblock %}
</body>
</html>
'''

INDEX_TEMPLATE = BASE_HTML.replace('{% block content %}{% endblock %}', '''
    <div class="search-box">
        <form action="/" method="get">
            <input type="text" name="q" value="{{ query }}" placeholder="Video ara...">
            <input type="submit" value="Ara">
        </form>
    </div>

    {% if results %}
        {% for video in results %}
            <div class="video-item">
                <a href="/watch?v={{ video.id }}">
                    <img src="{{ video.thumbnail }}" alt="thumb">
                    {{ video.title }}
                </a>
                <div style="color: #666; font-size: 10px; margin-top: 4px;">Kanal: {{ video.uploader }}</div>
                <div class="clear"></div>
            </div>
        {% endfor %}
    {% endif %}
''')

WATCH_TEMPLATE = BASE_HTML.replace('{% block content %}{% endblock %}', '''
    <a href="javascript:history.back()" class="btn-back">&laquo; Geri Dön</a>
    <div style="background:#fff; padding:8px; font-size:12px; border:1px solid #ccc; margin-bottom:10px;">
        <b>{{ video.title }}</b><br>
        <span style="font-size:10px; color:#666;">Kanal: {{ video.uploader }}</span>
    </div>
    
    <div style="text-align:center; background:#fff; padding:10px; border:1px solid #ccc;">
        <img src="{{ video.thumbnail }}" width="180" style="border:1px solid #999; margin-bottom:5px;"><br>
        
        <div class="quality-box">
            <b style="font-size:11px;">Kalite Seçin:</b><br>
            <a href="/watch?v={{ video.id }}&fmt=17" class="q-btn" style="background:{% if current_fmt == '17' %}#007bff{% else %}#e0e0e0{% endif %}; color:{% if current_fmt == '17' %}#fff{% else %}#000{% endif %};">144p (En Hafif)</a>
            <a href="/watch?v={{ video.id }}&fmt=18" class="q-btn" style="background:{% if current_fmt == '18' %}#007bff{% else %}#e0e0e0{% endif %}; color:{% if current_fmt == '18' %}#fff{% else %}#000{% endif %};">360p (Net)</a>
            <a href="/watch?v={{ video.id }}&fmt=auto" class="q-btn" style="background:{% if current_fmt == 'auto' %}#007bff{% else %}#e0e0e0{% endif %}; color:{% if current_fmt == 'auto' %}#fff{% else %}#000{% endif %};">Otomatik</a>
        </div>
        
        <a href="/stream.mp4?v={{ video.id }}&fmt={{ current_fmt }}" class="play-btn">
            ▶ Oynat (QQPlayer)
        </a>
        
        <a href="/download.mp4?v={{ video.id }}&fmt={{ current_fmt }}" class="dl-btn">
            💾 Videoyu Telefona İndir (MP4)
        </a>
    </div>
''')

def clean_filename(title):
    """HTTP Header hatası vermesin diye Türkçe/Unicode karakterleri ASCII'ye çevirir."""
    replacements = {
        'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S',
        'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
    }
    for tr, en in replacements.items():
        title = title.replace(tr, en)
    
    cleaned = "".join([c for c in title if c.isascii() and (c.isalnum() or c in (' ', '_', '-'))]).strip()
    return cleaned or "video"

def get_format_spec(fmt):
    if fmt == '17':
        return '17/worst[ext=mp4]'
    elif fmt == '18':
        return '18/worst[ext=mp4]'
    else:
        return '18/17/worst[ext=mp4]/worst'

@app.route('/')
def index():
    query = request.args.get('q', '')
    results = []
    if query:
        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch10:{query}", download=False)
                if 'entries' in info:
                    for entry in info['entries']:
                        results.append({
                            'id': entry.get('id'),
                            'title': entry.get('title', 'Başlıksız'),
                            'uploader': entry.get('uploader', 'Bilinmiyor'),
                            'thumbnail': f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg"
                        })
            except Exception as e:
                print(f"Arama hatası: {e}")

    return render_template_string(INDEX_TEMPLATE, query=query, results=results)

@app.route('/watch')
def watch():
    video_id = request.args.get('v')
    fmt = request.args.get('fmt', '17')
    if not video_id:
        return redirect('/')
    
    video_info = {
        'id': video_id,
        'title': 'Video Yükleniyor...',
        'uploader': 'YouTube',
        'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    }
    
    ydl_opts = {'quiet': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_id, download=False)
            video_info['title'] = info.get('title', 'Video')
            video_info['uploader'] = info.get('uploader', 'Bilinmiyor')
        except Exception:
            pass

    return render_template_string(WATCH_TEMPLATE, video=video_info, current_fmt=fmt)

@app.route('/stream.mp4')
@app.route('/stream')
def stream():
    video_id = request.args.get('v')
    fmt = request.args.get('fmt', '17')
    if not video_id:
        return "Video ID eksik", 400

    ydl_opts = {
        'quiet': True,
        'format': get_format_spec(fmt),
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_id, download=False)
            stream_url = info.get('url')
            
            if stream_url:
                req = requests.get(stream_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
                return Response(
                    stream_with_context(req.iter_content(chunk_size=1024 * 64)),
                    content_type='video/mp4'
                )
            else:
                return "Video akış adresi alınamadı", 500
        except Exception as e:
            return f"Akış hatası: {str(e)}", 500

@app.route('/download.mp4')
@app.route('/download')
def download():
    video_id = request.args.get('v')
    fmt = request.args.get('fmt', '17')
    if not video_id:
        return "Video ID eksik", 400

    ydl_opts = {
        'quiet': True,
        'format': get_format_spec(fmt),
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_id, download=False)
            stream_url = info.get('url')
            title = info.get('title', video_id)
            
            # Türkçe karakterleri temizleyip ASCII uyumlu dosya adı üretiyoruz:
            safe_filename = clean_filename(title)
            
            if stream_url:
                req = requests.get(stream_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
                return Response(
                    stream_with_context(req.iter_content(chunk_size=1024 * 64)),
                    content_type='application/octet-stream',
                    headers={"Content-Disposition": f'attachment; filename="{safe_filename}.mp4"'}
                )
            else:
                return "Video adresi alınamadı", 500
        except Exception as e:
            return f"İndirme hatası: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)