from flask import Flask, request, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
import base64
import os
import scraper  # Assuming scraper.py is in same directory

app = Flask(__name__)

# Temporary in-memory database (you can switch back to Firebase if needed)
user_sessions = {}

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

def get_user(phone):
    if phone not in user_sessions:
        user_sessions[phone] = {
            "step": "start",
            "username": None,
            "password": None,
            "semester": None
        }
    return user_sessions[phone]

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "").split(":")[-1]
    resp = MessagingResponse()
    msg = resp.message()
    data = get_user(sender)

    if incoming_msg.lower() == "help":
        msg.body("Available commands:\n1. reset username\n2. reset password\n3. reset semester\n4. reset all")
        data["step"] = "awaiting_help"
        return str(resp)

    if data["step"] == "awaiting_help":
        if "username" in incoming_msg.lower():
            msg.body("Please enter your new username:")
            data["step"] = "awaiting_username"
        elif "password" in incoming_msg.lower():
            msg.body("Please enter your new password:")
            data["step"] = "awaiting_password"
        elif "semester" in incoming_msg.lower():
            msg.body("Please enter your semester code (e.g., 2025EVESem):")
            data["step"] = "awaiting_semester"
        elif "all" in incoming_msg.lower():
            data.update({"username": None, "password": None, "semester": None, "step": "start"})
            msg.body("All data cleared. Type anything to start again.")
        else:
            msg.body("Unknown command. Send 'help'.")
        return str(resp)

    if data["step"] == "awaiting_username":
        data["username"] = incoming_msg
        data["step"] = "awaiting_password"
        msg.body("Enter your Password:")
        return str(resp)

    if data["step"] == "awaiting_password":
        data["password"] = incoming_msg
        data["step"] = "awaiting_semester"
        msg.body("Enter your Semester Code (e.g., 2025EVESem):")
        return str(resp)

    if data["step"] == "awaiting_semester":
        data["semester"] = incoming_msg
        data["step"] = "ready"
        msg.body("All credentials saved. Type anything to begin login.")
        return str(resp)
        
    if data["username"] is None:
        msg.body("Enter your Username:")
        data["step"] = "awaiting_username"
        return str(resp)

    if data["step"] == "ready":
        msg.body("Logging in... Please wait.")
        driver = scraper.launch_driver()
        try:
            captcha_base64 = scraper.fetch_captcha_base64(driver)
            if captcha_base64:
                if not os.path.exists("static"):
                    os.makedirs("static")
                img_path = f"static/{sender}_captcha.jpeg"
                with open(img_path, "wb") as f:
                    f.write(base64.b64decode(captcha_base64))
                msg.media(f"https://jiit-attendance-bot.onrender.com/static/{sender}_captcha.jpeg")
                msg.body("Please enter CAPTCHA text shown above:")
                data["step"] = "awaiting_captcha"
            else:
                msg.body("Failed to fetch captcha.")
        except Exception as e:
            msg.body(f"Error during login: {e}")
        driver.quit()
        return str(resp)

    if data["step"] == "awaiting_captcha":
        captcha = incoming_msg
        driver = scraper.launch_driver()
        try:
            result = scraper.login_and_fetch_attendance(
                driver,
                captcha,
                data["username"],
                data["password"],
                data["semester"]
            )
            msg.body(result)
            data["step"] = "done"
        except Exception as e:
            msg.body(f"Error retrieving attendance: {e}")
        driver.quit()
        return str(resp)

    msg.body("Session completed. Send 'help' or anything to restart.")
    data["step"] = "start"
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
