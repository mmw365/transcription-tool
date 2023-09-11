from configparser import ConfigParser
import sys
import openai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import requests
import json
import os
from ftplib import FTP

config = ConfigParser()

def main():
    if len(sys.argv) < 2:
        sys.exit()
    filename = sys.argv[1]
    config.read("app.ini")

    basename = os.path.basename(filename)
    filename_all_text = os.path.splitext(basename)[0] + "_all.txt"
    filename_sum_text = os.path.splitext(basename)[0] + "_sum.txt"
    filename_html = os.path.splitext(basename)[0] + ".html"

    init_openai()

    if config['setting']['skipWisper'] == 'Y':
        with open(filename_all_text, 'r', encoding='utf-8') as f:
            transcript = f.read()
    else:
        transcript = send_to_whisper(filename, filename_all_text)

    if config['setting']['skipGpt'] == 'Y':
        with open(filename_sum_text, 'r', encoding='utf-8') as f:
            summary = f.read()
    else:
        summary = send_to_gpt(transcript, filename_sum_text)

    addUrlLink = False
    if config['setting']['uploadHtml'] == 'Y':
        create_html(summary, filename_html)
        ftp_html(filename_html)
        addUrlLink = True

    if config['setting']['sendAudioFile'] == 'Y':
        send_audio_file(filename)

    if config['setting']['sendEmail'] == 'Y':
        send_email_message(summary)
    
    if config['setting']['sendLine'] == 'Y':
        send_line_massage(filename_html, summary, addUrlLink)

def init_openai():
    openai.organization = config['openai']['organization']
    openai.api_key = config['openai']['api_key']

def send_to_whisper(filename, filename_all_text):
    audio_file= open(filename, "rb")
    transcript = openai.Audio.transcribe("whisper-1", audio_file)
    print("--- 文字起こし ---")
    print(transcript["text"])
    with open(filename_all_text, 'w', encoding='utf-8') as f:
        f.write(transcript["text"])
    return transcript["text"]

def send_to_gpt(transcript, filename_sum_text):
    sample_all = ""
    sample_sum = ""

    # Including sample in message may cause low quality output
    if os.path.exists("sample_all.txt"):
        with open('sample_all.txt', 'r', encoding='utf-8') as f:
            sample_all = f.read()
    if os.path.exists("sample_sum.txt"):
        with open('sample_sum.txt', 'r', encoding='utf-8') as f:
            sample_sum = f.read()

    prompt = \
'''
以下のニュースを重要なポイントを中心に複数の段落に分け、文字数が500文字から600文字の間で要約してください。段落の間には改行を2個入れてください。

条件:
・誤字や脱字があれば修正する
・重要なポイントを抽出し複数の段落に分ける
・段落の間には改行を2個入れる
・出力の文字数は500文字から600文字の間
・ニュースの要約の部分だけを出力する
・「以上、」から始まる、まとめの1文は出力しない

文章:
'''
    if sample_all != "" and sample_sum != "":
        messages=[
            {"role": "system", "content": "あなたは優秀な編集者です。条件に従い文章を要約します。"},
            {"role": "user", "content": prompt + sample_all},
            {"role": "assistant", "content": sample_sum},
            {"role": "user", "content": "文章:\n" + transcript},
        ]
    else:
        messages=[
            {"role": "system", "content": "あなたは優秀な編集者です。条件に従い文章を要約します。"},
            {"role": "user", "content": prompt + transcript},
        ]

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        # model="gpt-4",
        messages=messages,
        # temperature=0.1,
        top_p=0.1,
    )
    res = response["choices"][0]["message"]["content"]
    print("--- 要約 ---")
    print(res)
    with open(filename_sum_text, 'w', encoding='utf-8') as f:
        f.write(res)
    return res

def create_html(summary, filename_html):
    with open('base.html', 'r', encoding='utf-8') as file:
        html = file.read()

    html = html.replace("__PLACE_HOLDER__", summary)
    with open(filename_html, 'w', encoding='utf-8') as f:
        f.write(html)

def ftp_html(filename_html):
    ftp = FTP(config['ftp']['server'])
    ftp.login(config['ftp']['userid'], config['ftp']['password'])
    ftp.cwd(config['ftp']['uploadpath'])
    with open(filename_html, 'rb') as file:
        ftp.storbinary('STOR ' + filename_html, file)
    ftp.quit()

def send_audio_file(filename):
    msg = MIMEMultipart()
    msg['Subject'] = "録音データ"
    msg['To'] = config['mail']['to']
    msg['From'] = config['mail']['from']
    msg.attach(MIMEText("録音データです。"))

    with open(filename, "rb") as f:
        attachment = MIMEApplication(f.read())
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    server = smtplib.SMTP(config['mail']['server'], config['mail']['port'])
    server.starttls()
    server.ehlo()
    server.login(config['mail']['from'], config['mail']['password'])
    server.send_message(msg)
    server.quit()

def send_email_message(summary):
    msg = MIMEText(summary)
    msg['Subject'] = "要約データ"
    msg['To'] = config['mail']['to']
    msg['From'] = config['mail']['from']

    server = smtplib.SMTP(config['mail']['server'], config['mail']['port'])
    server.starttls()
    server.ehlo()
    server.login(config['mail']['from'], config['mail']['password'])
    server.send_message(msg)
    server.quit()

def send_line_massage(filename_html, summary, addUrlLink):
    # Define the URL where you want to send the JSON message
    url = config['line']['pushUrl']
    userId = config['line']['sendToUserId']

    textMessage = summary
    if addUrlLink:
        textMessage += "\n\n" + config['ftp']['uploadUrl'] + filename_html

    pushData = {
        "to": userId,
        "messages": [{"type": "text", "text": textMessage,},],
    }

    json_data = json.dumps(pushData)

    # Send the JSON message
    response = requests.post(url, data=json_data, headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + config['line']['accessToken']
    ,
    })

    # Print the response
    print(response.text)

if __name__ == "__main__":
    main()