from flask import Flask, request, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
import base64
import os
import scraper  # Assuming scraper.py is in same directory

app = Flask(__name__)

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

    # Step 1: Handle help commands
    if incoming_msg.lower() == "help":
        msg.body("Available commands:\n1. reset username\n2. reset password\n3. reset semester\n4. reset all")
        data["step"] = "awaiting_help"
        return str(resp)

    # Step 2: Handle help response
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
            data.update({"username": None, "password": None, "semester": None, "step": "awaiting_username"})
            msg.body("All data cleared. Please enter your username:")
        else:
            msg.body("Unknown command. Send 'help' again.")
        return str(resp)

    # Step 3: Collect credentials
    if data["step"] == "awaiting_username":
        data["username"] = incoming_msg
        data["step"] = "awaiting_password"
        msg.body("Enter your password:")
        return str(resp)

    if data["step"] == "awaiting_password":
        data["password"] = incoming_msg
        data["step"] = "awaiting_semester"
        msg.body("Enter your semester code (e.g., 2025EVESem):")
        return str(resp)

    if data["step"] == "awaiting_semester":
        data["semester"] = incoming_msg
        data["step"] = "ready"
        msg.body("All credentials saved. Type anything to begin login.")
        return str(resp)

    # Step 4: Ask for missing credentials
    if not all([data["username"], data["password"], data["semester"]]):
        if not data["username"]:
            data["step"] = "awaiting_username"
            msg.body("Enter your username:")
        elif not data["password"]:
            data["step"] = "awaiting_password"
            msg.body("Enter your password:")
        elif not data["semester"]:
            data["step"] = "awaiting_semester"
            msg.body("Enter your semester code:")
        return str(resp)


    # Begin login
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

    msg.body("Session completed or unknown input. Send 'help' or type anything to restart.")
    data["step"] = "start"
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
