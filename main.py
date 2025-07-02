from flask import Flask, request, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
import base64
import os
import scraper  # scraper.py should be in the same directory

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

    # 🔁 Hard reset for all users (admin use)
    if incoming_msg.lower() == "force reset":
        user_sessions.clear()
        msg.body("All user sessions cleared. Start again with username.")
        return str(resp)

    # 🔁 Reset for current user only
    if incoming_msg.lower() == "restart":
        user_sessions[sender] = {
            "step": "start",
            "username": None,
            "password": None,
            "semester": None
        }
        msg.body("Session reset. Please enter your username:")
        return str(resp)

    data = get_user(sender)

    # 🆘 Help Command
    if incoming_msg.lower() == "help":
        msg.body(
            "Commands:\n"
            "• restart - Reset your session\n"
            "• help - Show this menu\n"
            "• reset username/password/semester/all"
        )
        data["step"] = "awaiting_help"
        return str(resp)

    # 🛠 Help response handling
    if data["step"] == "awaiting_help":
        if "username" in incoming_msg.lower():
            data["step"] = "awaiting_username"
            msg.body("Please enter your new username:")
        elif "password" in incoming_msg.lower():
            data["step"] = "awaiting_password"
            msg.body("Please enter your new password:")
        elif "semester" in incoming_msg.lower():
            data["step"] = "awaiting_semester"
            msg.body("Choose your semester:\n1. 2025ODDSEM\n2. 2025EVESEM\n3. 2024ODDSEM\nReply with 1, 2 or 3.")
        elif "all" in incoming_msg.lower():
            data.update({"username": None, "password": None, "semester": None, "step": "awaiting_username"})
            msg.body("All credentials cleared. Please enter your username:")
        else:
            msg.body("Unknown command. Send 'help' again.")
        return str(resp)

    # ✍ Step 0: Ask for username
    if not data["username"] or data["step"] == "awaiting_username":
        if data["step"] != "awaiting_username":
            data["step"] = "awaiting_username"
            msg.body("Please enter your username:")
        else:
            data["username"] = incoming_msg
            data["step"] = "awaiting_password"
            msg.body("Enter your password:")
        return str(resp)

    # ✍ Step 1: Ask for password
    if not data["password"] or data["step"] == "awaiting_password":
        if data["step"] != "awaiting_password":
            data["step"] = "awaiting_password"
            msg.body("Please enter your password:")
        else:
            data["password"] = incoming_msg
            data["step"] = "awaiting_semester"
            msg.body("Choose your semester:\n1. 2025ODDSEM\n2. 2025EVESEM\n3. 2024ODDSEM\nReply with 1, 2 or 3.")
        return str(resp)

    # ✍ Step 2: Ask for semester selection
    if not data["semester"] or data["step"] == "awaiting_semester":
        semester_map = {
            "1": "2025ODDSEM",
            "2": "2025EVESEM",
            "3": "2024ODDSEM"
        }
        choice = incoming_msg.strip()
        if choice in semester_map:
            data["semester"] = semester_map[choice]
            data["step"] = "ready"
            msg.body(f"Semester set to {semester_map[choice]}.\nAll credentials saved. Type anything to login.")
        else:
            data["step"] = "awaiting_semester"
            msg.body("Invalid choice. Reply with:\n1. 2025ODDSEM\n2. 2025EVESEM\n3. 2024ODDSEM")
        return str(resp)

    # 🚀 Begin login
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
                msg.body("Enter CAPTCHA shown above:")
                data["step"] = "awaiting_captcha"
            else:
                msg.body("Failed to fetch CAPTCHA.")
        except Exception as e:
            msg.body(f"Error during login: {e}")
            print(f"[ERROR] Login failed: {e}")
        driver.quit()
        return str(resp)

    # 🔐 Login with CAPTCHA
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
            print(f"[ERROR] Attendance fetch failed: {e}")
        driver.quit()
        return str(resp)

    # Final fallback
    msg.body("Session completed or unknown input. Send 'restart' or 'help' to continue.")
    data["step"] = "start"
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
