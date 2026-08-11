import os
from flask import Flask, render_template_string, request, Response
import requests
import yt_dlp

app = Flask(__name__)

# Android 2.3 tarayıcıları için ultra hafif HTML arayüzü
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Retro Tube</title>
    <style>
        body { font-family: sans-serif; background: #121212; color: #fff; text-align: center; padding: 10px; margin:0; }
        input[type="text"] { padding: 8px; font-size: 14px; width: 60%; }
        button { padding: 8px 12px; font-size: 14px; background: #ff0000; color: #fff; border: none; cursor: pointer; }
        .card { border: 1px solid #333; margin: 10px auto; padding: 10px; background: #1e1e1e; max-width: 500px; text-align: left; }
        a.play-btn { display: inline-block; padding: 6px 12px; background: #0088cc; color: #fff; text-decoration: none; font-weight: bold; border-radius: 3px; margin-top: 5px; }
    </style>
</head>
<body>
    <h2>📺 Retro Tube</h2>
    <form action="/" method="get">
        <input type="text" name="q" placeholder="Video ara veya YouTube linki yapıştır..." value="{{ query }}">
        <button type="submit">Ara</button>
    </form>
    <hr style="border-color:#333;">

    {% if videos %}
        {% for v in videos %}
            <div class="card">
                <strong>{{ v.title }}</strong><br>
                <small style="color:#aaa;">Kanal: {{ v.uploader }}</small><br>
                <a class="play-btn" href="/stream/{{ v.id }}">▶️ QQPlayer İle Oynat</a>
                <a class="play-btn" style="background:#444;" href="/watch/{{ v.id }}">🌐 Web'de Aç</a>
            </div>
        {% endfor %}
    {% endif %}
</body>
</html>
"""


def get_yt_stream_info(video_id):
  """YouTube video bilgilerini ve eski cihazlara uygun akış bağlantısını çeker."""
  url = f'https://www.youtube.com/watch?v={video_id}'
  ydl_opts = {
      # 18: 360p MP4 (H.264/AAC) -> Galaxy Y ve QQPlayer için EN UYUMLU formattır
      # 17: 144p 3GP -> Aşırı düşük bağlantılar için yedek
      'format': '18/17/worst[ext=mp4]/worst',
      'quiet': True,
      'no_warnings': True,
  }
  with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    return info.get('url'), info.get('http_headers', {})


@app.route('/')
def index():
  query = request.args.get('q', '')
  videos = []
  if query:
    # Arama query'si veya doğrudan link kontrolü
    ydl_opts = {'quiet': True, 'extract_flat': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      search_target = query if 'youtube.com' in query else f'ytsearch5:{query}'
      res = ydl.extract_info(search_target, download=False)
      entries = (
          res.get('entries', []) if 'entries' in res else [res]
      )  # Tek video veya arama
      for entry in entries:
        if entry:
          videos.append({
              'id': entry.get('id'),
              'title': entry.get('title', 'Başlıksız Video'),
              'uploader': entry.get('uploader', 'Bilinmiyor'),
          })
  return render_template_string(HTML_TEMPLATE, query=query, videos=videos)


@app.route('/stream/<video_id>')
def proxy_stream(video_id):
  """QQPlayer / Eski Medya Oynatıcılar için Proxy Akışı (YouTube 403 Engeli Aşılır)."""
  try:
    direct_url, yt_headers = get_yt_stream_info(video_id)

    # Oynatıcıdan gelen Range header'ını (sarma/buffering isteğini) yakalayalım
    req_headers = {
        'User-Agent': yt_headers.get('User-Agent', 'Mozilla/5.0'),
    }
    if 'Range' in request.headers:
      req_headers['Range'] = request.headers['Range']

    # YouTube'dan akışı canlı çekiyoruz
    r = requests.get(direct_url, headers=req_headers, stream=True, timeout=15)

    # Başlıkları medya oynatıcıya aktaralım
    response_headers = {
        'Content-Type': r.headers.get('Content-Type', 'video/mp4'),
        'Accept-Ranges': 'bytes',
    }
    if 'Content-Length' in r.headers:
      response_headers['Content-Length'] = r.headers['Content-Length']
    if 'Content-Range' in r.headers:
      response_headers['Content-Range'] = r.headers['Content-Range']

    return Response(
        r.iter_content(chunk_size=64 * 1024),
        status=r.status_code,
        headers=response_headers,
        direct_passthrough=True,
    )
  except Exception as e:
    return f'Akış Hatası: {str(e)}', 500


@app.route('/watch/<video_id>')
def watch(video_id):
  """Basit HTML5 Video Sayfası."""
  return render_template_string(
      """
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>Oynatıcı</title></head>
    <body style="background:#000; color:#fff; text-align:center; padding-top:20px;">
        <video controls autoplay width="100%" height="auto">
            <source src="/stream/{{ video_id }}" type="video/mp4">
            Tarayıcınız video etiketini desteklemiyor.
        </video>
        <br><br>
        <a style="color:#0088cc;" href="/stream/{{ video_id }}">Harici Oynatıcıda (QQPlayer) Aç</a> | 
        <a style="color:#aaa;" href="/">Ana Sayfa</a>
    </body>
    </html>
    """,
      video_id=video_id,
  )


if __name__ == '__main__':
  # Render'ın atadığı dinamik portu dinler
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)