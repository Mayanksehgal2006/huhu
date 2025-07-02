# main.py
import os
import logging
from flask import Flask, request, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
import firebase_admin
from firebase_admin import credentials, db
from scraper import launch_driver, get_captcha_image, login_and_fetch_attendance

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

cred = credentials.Certificate("/etc/secrets/firebase_credentials.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://jiit-attendance-bot-default-rtdb.asia-southeast1.firebasedatabase.app'
})

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

def get_user_data(phone):
    ref = db.reference(f'users/{phone}')
    user = ref.get()
    default = {"phone": phone, "step": "start", "username": None, "password": None, "semester": None}
    return {**default, **(user or {})}

def update_user_data(phone, data):
    ref = db.reference(f'users/{phone}')
    ref.set(data)


@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "").split(":")[-1]
    resp = MessagingResponse()
    msg = resp.message()

    data = get_user_data(sender)

    # Help flow
    if incoming_msg.lower() == "help":
        msg.body("Available commands:\n1. reset username\n2. reset password\n3. reset semester\n4. reset all")
        data["step"] = "awaiting_help"
        update_user_data(sender, data)
        return str(resp)

    if data["step"] == "awaiting_help":
        if "username" in incoming_msg.lower():
            data["step"] = "awaiting_username"
            msg.body("Please enter your new username:")
        elif "password" in incoming_msg.lower():
            data["step"] = "awaiting_password"
            msg.body("Please enter your new password:")
        elif "semester" in incoming_msg.lower():
            data["step"] = "awaiting_semester"
            msg.body("Please enter your semester code (e.g., 2025EVESem):")
        elif "all" in incoming_msg.lower():
            data.update({"username": None, "password": None, "semester": None, "step": "start"})
            msg.body("All data reset. Start again.")
        else:
            msg.body("Invalid command. Type 'help' for options.")
        update_user_data(sender, data)
        return str(resp)

    # Credential collection
    if data["username"] is None:
        data["step"] = "awaiting_username"
        msg.body("Enter your Username:")
        update_user_data(sender, data)
        return str(resp)

    if data["step"] == "awaiting_username":
        data["username"] = incoming_msg
        data["step"] = "awaiting_password"
        msg.body("Enter your Password:")
        update_user_data(sender, data)
        return str(resp)

    if data["step"] == "awaiting_password":
        data["password"] = incoming_msg
        data["step"] = "awaiting_semester"
        msg.body("Enter your Semester Code:")
        update_user_data(sender, data)
        return str(resp)

    if data["step"] == "awaiting_semester":
    data["semester"] = incoming_msg
    data["step"] = "start"
    update_user_data(sender, data)
    msg.body("All credentials received. Type anything to continue and fetch attendance.")
    return str(resp)


    if data["step"] == "start":
        msg.body("Fetching CAPTCHA, please wait...")
        driver = launch_driver()
        img_data = get_captcha_image(driver)

        if img_data:
            if not os.path.exists("static"):
                os.makedirs("static")
            path = f"static/{sender}_captcha.jpeg"
            with open(path, "wb") as f:
                f.write(img_data)
            msg.media(f"https://jiit-attendance-bot.onrender.com/static/{sender}_captcha.jpeg")
            msg.body("Enter the CAPTCHA text:")
            data["step"] = "awaiting_captcha"
        else:
            msg.body("Failed to get CAPTCHA.")
        update_user_data(sender, data)
        driver.quit()
        return str(resp)

    if data["step"] == "awaiting_captcha":
        captcha = incoming_msg
        driver = launch_driver()
        result = login_and_fetch_attendance(driver, data["username"], data["password"], captcha, data["semester"])
        driver.quit()

        if result:
            msg.body(result)
            data["step"] = "done"
        else:
            msg.body("Login failed or CAPTCHA incorrect. Type 'help' to reset credentials.")
            data["step"] = "start"

        captcha_path = f"static/{sender}_captcha.jpeg"
        if os.path.exists(captcha_path):
            os.remove(captcha_path)

        update_user_data(sender, data)
        return str(resp)

    msg.body("Unknown state. Type any message to start again.")
    data["step"] = "start"
    update_user_data(sender, data)
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)

