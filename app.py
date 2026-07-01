from flask import Flask, jsonify, request, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_mqtt import Mqtt
from flask_cors import CORS
import datetime
import requests  # Telegram Bot ဆီ စာလှမ်းပို့ရန်အတွက်

app = Flask(__name__, template_folder='.')
CORS(app)

# ၁။ Database Setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smarthome_pro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ၂။ MQTT Setup
app.config['MQTT_BROKER_URL'] = 'broker.hivemq.com'
app.config['MQTT_BROKER_PORT'] = 1883
app.config['MQTT_USERNAME'] = ''
app.config['MQTT_PASSWORD'] = ''
app.config['MQTT_KEEPALIVE'] = 60
app.config['MQTT_TLS_ENABLED'] = False

db = SQLAlchemy(app)
mqtt = Mqtt(app)

# 🌟 TELEGRAM CONFIGURATION
# စမ်းသပ်ဖို့အတွက် Token နဲ့ Chat ID ကို ထည့်ရမယ် (လောလောဆယ် အလွတ်ထားပေးမယ် သားရီး)
TELEGRAM_BOT_TOKEN = 'YOUR_BOT_TOKEN'
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'


def send_telegram_alert(message):
    if TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN':
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Telegram Error: {e}")


# -------------------------------------------------------------
# 💾 DATABASE MODELS
# -------------------------------------------------------------
class DeviceStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(50), nullable=False)


class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.now)


# -------------------------------------------------------------
# 🌐 WEB PAGE & API ROUTES
# -------------------------------------------------------------

@app.route('/')
def home():
    with open('index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    return render_template_string(html_content)


# (က) API - Get Status (ပစ္စည်းအားလုံး၏ Status နှင့် Sensor တန်ဖိုးများ ပေးပို့ခြင်း)
@app.route('/api/status', methods=['GET'])
def get_all_status():
    devices = DeviceStatus.query.all()
    status_dict = {d.device_name: d.status for d in devices}

    # စနစ်သစ်အတွက် Feature စာရင်းအမှန် ကြိုတင်အထိုင်ချခြင်း
    all_features = {
        'door_lock': 'LOCKED',  # LOCKED / UNLOCKED
        'room1_light': 'OFF', 'room2_light': 'OFF', 'room3_light': 'OFF',
        'room1_fan': 'OFF', 'room2_fan': 'OFF', 'room3_fan': 'OFF',
        'current_temp': '28',  # ESP32 မှ တက်လာမည့် လက်ရှိအပူချိန် (°C)
        'fan_threshold': '30',  # ဝက်ဘ်ဆိုက်မှ လှမ်းသတ်မှတ်မည့် ပန်ကာလည်ရမည့် အပူချိန် (°C)
        'water_level': '100',  # ရေ Level ရာခိုင်နှုန်း (0% - 100%)
        'water_motor': 'OFF',  # ON / OFF
        'gas_status': 'SAFE',  # SAFE / DANGER
        'trash_status': 'EMPTY',  # EMPTY / FULL
        'weather_status': 'SUNNY',  # SUNNY / RAINY
        'clothes_line': 'OUTSIDE'  # OUTSIDE / INSIDE
    }

    changed = False
    for dev, default_val in all_features.items():
        if dev not in status_dict:
            new_dev = DeviceStatus(device_name=dev, status=default_val)
            db.session.add(new_dev)
            status_dict[dev] = default_val
            changed = True
    if changed:
        db.session.commit()

    return jsonify(status_dict)


# (ခ) API - Control (မီး၊ တံခါး၊ အဝတ်လှန်းစင်များအား ဝက်ဘ်ဆိုက်မှ လှမ်းထိန်းခြင်း)
@app.route('/api/control', methods=['POST'])
def control_device():
    data = request.get_json()
    device = data.get('device')
    action = data.get('action')

    dev_status = DeviceStatus.query.filter_by(device_name=device).first()
    if dev_status:
        dev_status.status = action

        log_text = f"Website မှ {device} ကို {action} သို့ အမိန့်ပေးလိုက်ပါသည်"
        db.session.add(SystemLog(activity=log_text))
        db.session.commit()

        # ESP32 ဆီသို့ MQTT အမိန့်စာ ပစ်လွှတ်ခြင်း
        mqtt.publish(f"tharyee/smarthome/{device}", action)
        return jsonify({"message": "Success"})
    return jsonify({"error": "Not found"}), 404


# (ဂ) API - Set Fan Threshold (ဝက်ဘ်ဆိုက်မှ ပန်ကာလည်မည့် အပူချိန် ကိန်းဂဏန်း လှမ်းသတ်မှတ်ခြင်း)
@app.route('/api/threshold', methods=['POST'])
def set_threshold():
    data = request.get_json()
    val = data.get('value')  # ဥပမာ - "32"

    dev_status = DeviceStatus.query.filter_by(device_name='fan_threshold').first()
    if dev_status:
        dev_status.status = str(val)
        db.session.add(
            SystemLog(activity=f"Website မှ ပန်ကာလည်မည့် အပူချိန်သတ်မှတ်ချက်ကို {val}°C သို့ ပြောင်းလိုက်သည်"))
        db.session.commit()

        # ESP32 ဘုတ်ဆီသို့ သတ်မှတ်အပူချိန်အသစ်အား MQTT ဖြင့် ချက်ချင်းလှမ်းပို့ခြင်း
        mqtt.publish("tharyee/smarthome/fan_threshold", str(val))
        return jsonify({"message": "Threshold updated successfully"})
    return jsonify({"error": "Failed"}), 400


# (ဃ) API - Get Logs
@app.route('/api/logs', methods=['GET'])
def get_logs():
    logs = SystemLog.query.order_by(SystemLog.timestamp.desc()).limit(12).all()
    logs_list = [{"activity": l.activity, "time": l.timestamp.strftime('%H:%M:%S')} for l in logs]
    return jsonify(logs_list)


# -------------------------------------------------------------
# 📡 MQTT RECEIVER LOGIC (ESP32 ထံမှ တက်လာမည့် ဒေတာများကို ဖမ်းယူခြင်း)
# -------------------------------------------------------------
@mqtt.on_connect()
def handle_connect(client, userdata, flags, rc):
    mqtt.subscribe("tharyee/smarthome/telemetry/#")


@mqtt.on_message()
def handle_mqtt_message(client, userdata, message):
    topic = message.topic
    payload = message.payload.decode()
    device = topic.split('/')[-1]  # ဆင်ဆာအမည် ခွဲထုတ်ခြင်း

    with app.app_context():
        dev_status = DeviceStatus.query.filter_by(device_name=device).first()
        if dev_status:
            old_status = dev_status.status
            dev_status.status = payload

            # ဒေတာ တကယ်ပြောင်းလဲသွားမှသာ Log မှတ်ပြီး အလုပ်လုပ်မည့် Logic
            if old_status != payload:
                log_text = f"ဆင်ဆာဝင်ရိုး: [{device}] အခြေအနေ -> {payload}"

                # 🗑️ စမတ်အမှိုက်ပုံးပြည့်လျှင် Telegram သို့ စာပို့ခြင်း
                if device == "trash_status" and payload == "FULL":
                    log_text = "🗑️ Smart Trash Can is FULL! (အမှိုက်ပုံး ပြည့်သွားပါပြီ)"
                    send_telegram_alert(
                        "⚠️ အကြောင်းကြားစာ: အိမ်က စမတ်အမှိုက်ပုံး ပြည့်သွားပါပြီ သားရီး၊ သွားသွန်ပေးပါဦး!")

                # 🚨 Gas ယိုစိမ့်မှု Alert
                elif device == "gas_status" and payload == "DANGER":
                    log_text = "🚨 WARNING: Gas/Smoke Detected! (အိမ်ထဲတွင် ဂက်စ်ယိုစိမ့်မှုကြောင့် Alarm မြည်နေသည်)"
                    send_telegram_alert(
                        "🚨 အရေးပေါ်သတိပေးချက်: အိမ်ထဲတွင် ဂက်စ်ယိုစိမ့်မှု (သို့မဟုတ်) မီးခိုးများ တွေ့ရှိရသဖြင့် အချက်ပေးသံ မြည်နေပါသည်!")

                # 💧 ရေ Level အခြေအနေအရ မော်တာတုံ့ပြန်မှု
                elif device == "water_level" and int(payload) <= 10:  # ရေ ၁၀ ရာခိုင်နှုန်းအောက် ရောက်လျှင်
                    log_text = f"💧 ရေနည်းနေပါသည် ({payload}%) - ရေမော်တာကို အော်တို မောင်းနှင်နေပါသည်"
                elif device == "water_level" and int(payload) >= 100:  # ရေပြည့်လျှင်
                    log_text = "💧 ရေတိုင်ကီ ပြည့်သွားပါပြီ (100%) - ရေမော်တာကို အော်တို ပိတ်လိုက်ပါပြီ"

                # 🌧️ မိုးရွာ၍ အဝတ်ရုတ်ခြင်း
                elif device == "weather_status" and payload == "RAINY":
                    log_text = "🌧️ မိုးရွာလာသဖြင့် အဝတ်လှန်းစင်အား အော်တို ရုတ်လိုက်ပါသည်"

                db.session.add(SystemLog(activity=log_text))
            db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)