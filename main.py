from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from tinydb import TinyDB, Query
import base64
import time
import os

app = Flask(__name__)

db = TinyDB('session_db.json')
User = Query()

def get_user_data(phone):
    result = db.get(User.phone == phone)
    if not result:
        return {
            "phone": phone,
            "step": "start",
            "username": None,
            "password": None,
            "semester": None,
            "captcha_src": "",
        }
    return result

def update_user_data(phone, data):
    db.upsert(data, User.phone == phone)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "").split(":")[-1]
    resp = MessagingResponse()
    msg = resp.message()

    data = get_user_data(sender)

    if incoming_msg.lower() == "help":
        msg.body("Available commands:\n" +
                 "1. reset username\n" +
                 "2. reset password\n" +
                 "3. reset semester\n" +
                 "4. reset all\n" +
                 "Reply with your choice.")
        data["step"] = "awaiting_help"
        update_user_data(sender, data)
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
            data = get_user_data(sender)
            data.update({"username": None, "password": None, "semester": None, "step": "start"})
            msg.body("All credentials cleared. Please start over.")
        else:
            msg.body("Invalid command. Send 'help' to see options.")
        update_user_data(sender, data)
        return str(resp)

    if data["username"] is None:
        msg.body("Enter your Username:")
        data["step"] = "awaiting_username"
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
        msg.body("Enter your Semester Code (e.g., 2025EVESem):")
        update_user_data(sender, data)
        return str(resp)

    if data["step"] == "awaiting_semester":
        data["semester"] = incoming_msg
        data["step"] = "start"
        update_user_data(sender, data)

    if data["step"] == "start":
        msg.body("Logging in to JIIT portal... Please wait.")
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(options=options)

        driver.get("https://webportal.jiit.ac.in:6011/studentportal/#/login")
        time.sleep(5)

        captcha_img = driver.find_element(By.TAG_NAME, "img")
        src = captcha_img.get_attribute("src")

        if "base64" in src:
            img_data = base64.b64decode(src.split(",")[1])
            path = f"static/{sender}_captcha.jpeg"
            with open(path, "wb") as f:
                f.write(img_data)
            msg.media(f"https://jiit-attendance-bot.onrender.com/{path}")
            msg.body("Please reply with the CAPTCHA text.")
            data["step"] = "awaiting_captcha"
            update_user_data(sender, data)
        else:
            msg.body("Could not retrieve captcha. Please try again.")

    elif data["step"] == "awaiting_captcha":
        captcha = incoming_msg
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=options)
        driver.get("https://webportal.jiit.ac.in:6011/studentportal/#/login")
        time.sleep(5)

        driver.find_element(By.ID, "mat-input-0").send_keys(data["username"])
        driver.find_element(By.ID, "mat-input-1").send_keys(data["password"])
        driver.find_element(By.CSS_SELECTOR, "input.ng-pristine").send_keys(captcha)
        driver.find_element(By.CSS_SELECTOR, "button.ng-pristine").click()
        time.sleep(5)

        try:
            class_menu = driver.find_element(By.XPATH, "//*[text()='Class and Attendance']")
            driver.execute_script("arguments[0].click();", class_menu)
            time.sleep(1)

            attendance_link = driver.find_element(By.XPATH, "//*[text()='My Class Attendance by Student']")
            driver.execute_script("arguments[0].click();", attendance_link)
            time.sleep(3)

            select = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "mat-select"))
            )
            driver.execute_script("arguments[0].click();", select)
            time.sleep(1)

            sem_option = driver.find_element(By.XPATH, f"//*[contains(text(),'{data['semester']}')]")
            driver.execute_script("arguments[0].click();", sem_option)
            time.sleep(1)

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
            data["step"] = "done"
        except Exception as e:
            msg.body(f"Error retrieving attendance: {e}")

        update_user_data(sender, data)

    else:
        msg.body("Session ended or unknown command. Type any message to start again or 'help'.")
        data["step"] = "start"
        update_user_data(sender, data)

    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
