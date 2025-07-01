from config_handler import load_config, save_config
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from PIL import Image
import base64
import time
import os

app = Flask(__name__)

# In-memory storage for session and user data
session_data = {
    "step": "start",
    "captcha_src": "",
    "driver": None,
    "username": None,
    "password": None,
    "semester": None,
    "available_semesters": [],
    "retry_count": 0
}

@app.route("/", methods=["GET"])
def home():
    return "✅ Flask app is running! Use /whatsapp for POST messages."

@app.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_reply():
    if request.method == "GET":
        return "👋 This endpoint expects POST requests from Twilio or curl."
    incoming_msg = request.values.get("Body", "").strip()
    resp = MessagingResponse()
    msg = resp.message()

    if session_data.get("retry_count", 0) >= 3:
        msg.body("Too many failed attempts. Restarting session.")
        session_data.update({"step": "start", "username": None, "password": None, "semester": None, "retry_count": 0})
        return str(resp)

    # Help Section
    if incoming_msg.lower() == "help":
        msg.body("Available commands:\n" +
                 "1. reset username\n" +
                 "2. reset password\n" +
                 "3. reset semester\n" +
                 "4. reset all\n" +
                 "Reply with your choice.")
        session_data["step"] = "awaiting_help"
        return str(resp)

    if session_data["step"] == "awaiting_help":
        if "username" in incoming_msg.lower():
            msg.body("Please enter your new username:")
            session_data["step"] = "awaiting_username"
        elif "password" in incoming_msg.lower():
            msg.body("Please enter your new password:")
            session_data["step"] = "awaiting_password"
        elif "semester" in incoming_msg.lower():
            session_data["semester"] = None
            msg.body("Semester reset. Reply anything to restart.")
            session_data["step"] = "start"
        elif "all" in incoming_msg.lower():
            session_data.update({"username": None, "password": None, "semester": None})
            msg.body("All credentials cleared. Please start over.")
            session_data["step"] = "start"
        else:
            msg.body("Invalid command. Send 'help' to see options.")
        return str(resp)

    if session_data["username"] is None:
        msg.body("Enter your Username:")
        session_data["step"] = "awaiting_username"
        return str(resp)

    if session_data["step"] == "awaiting_username":
        session_data["username"] = incoming_msg
        msg.body("Enter your Password:")
        session_data["step"] = "awaiting_password"
        return str(resp)

    if session_data["step"] == "awaiting_password":
        session_data["password"] = incoming_msg
        session_data["step"] = "start"

    if session_data["step"] == "start":
        msg.body("Logging in to JIIT portal... Please wait.")
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(options=options)
        session_data["driver"] = driver

        driver.get("https://webportal.jiit.ac.in:6011/studentportal/#/login")
        time.sleep(5)

        captcha_img = driver.find_element(By.TAG_NAME, "img")
        src = captcha_img.get_attribute("src")

        if "base64" in src:
            session_data["captcha_src"] = src
            img_data = base64.b64decode(src.split(",")[1])
            with open("static/captcha.jpeg", "wb") as f:
                f.write(img_data)
            msg.media("https://yourdomain.com/static/captcha.jpeg")
            msg.body("Please reply with the CAPTCHA text.")
            session_data["step"] = "awaiting_captcha"
        else:
            msg.body("Could not retrieve captcha. Please try again.")

    elif session_data["step"] == "awaiting_captcha":
        captcha = incoming_msg
        driver = session_data["driver"]

        try:
            driver.find_element(By.ID, "mat-input-0").send_keys(session_data["username"])
            driver.find_element(By.ID, "mat-input-1").send_keys(session_data["password"])
            driver.find_element(By.CSS_SELECTOR, "input.ng-pristine").send_keys(captcha)
            driver.find_element(By.CSS_SELECTOR, "button.ng-pristine").click()
            time.sleep(5)

            driver.find_element(By.XPATH, "//*[text()='Class and Attendance']").click()
            time.sleep(1)
            driver.find_element(By.XPATH, "//*[text()='My Class Attendance by Student']").click()
            time.sleep(3)

            select = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "mat-select"))
            )
            driver.execute_script("arguments[0].click();", select)
            time.sleep(1)

            options = driver.find_elements(By.XPATH, "//mat-option")
            session_data["available_semesters"] = [opt.text for opt in options if opt.text.strip()]

            if not session_data["available_semesters"]:
                raise Exception("No semesters found.")

            sem_list = "\n".join(f"{i+1}. {sem}" for i, sem in enumerate(session_data["available_semesters"]))
            msg.body(f"Available semesters:\n{sem_list}\nReply with the number of the semester you want.")
            session_data["step"] = "awaiting_semester_choice"
        except Exception as e:
            session_data["retry_count"] += 1
            msg.body(f"Login failed or captcha incorrect. Error: {e}\nPlease send the correct CAPTCHA again.")
            session_data["step"] = "awaiting_captcha"

    elif session_data["step"] == "awaiting_semester_choice":
        try:
            choice = int(incoming_msg.strip()) - 1
            semester = session_data["available_semesters"][choice]
            session_data["semester"] = semester

            driver = session_data["driver"]
            driver.find_element(By.XPATH, f"//*[contains(text(),'{semester}')]").click()
            driver.find_element(By.XPATH, "//button[contains(text(),'Submit')]").click()
            time.sleep(3)

            table = driver.find_element(By.ID, "pn_id_4-table")
            rows = table.find_elements(By.TAG_NAME, "tr")

            output = "*Your Attendance:*\n"
            for r in rows[1:]:
                cols = r.find_elements(By.TAG_NAME, "td")
                sub = cols[1].text
                overall = cols[5].text
                output += f"{sub}: {overall}%\n"

            msg.body(output)
            session_data["step"] = "done"
        except Exception as e:
            session_data["retry_count"] += 1
            msg.body(f"Failed to retrieve attendance: {e}\nPlease select a valid semester number.")
            session_data["step"] = "awaiting_semester_choice"

    else:
        msg.body("Session ended. Send any message to start again or type 'help'.")
        if session_data.get("driver"):
            try:
                session_data["driver"].quit()
            except:
                pass
        session_data["step"] = "start"

    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
