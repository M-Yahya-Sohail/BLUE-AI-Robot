import tkinter as tk
import threading
import time
import sys
import json
import random
import subprocess
import requests
import base64
import speech_recognition as sr
from gpiozero import Robot, DistanceSensor
from llama_cpp import Llama
from ultralytics import YOLO  

# ==========================================
# ⚙️  CONFIGURATION
# ==========================================
# 1. HARDWARE PINS
LEFT_PINS = (27,17)
RIGHT_PINS = (22, 23)
TRIGGER_PIN = 25
ECHO_PIN = 24

# 2. NETWORK / API
LAPTOP_IP = "192.168.5.1"  # <--- CHECK IP
LAPTOP_PORT = "11434"
LAPTOP_URL = f"http://{LAPTOP_IP}:{LAPTOP_PORT}/api/chat"

# 3. LOCAL BRAIN
MODEL_PATH = "/home/pi/qwen.gguf"
YOLO_MODEL_PATH = "yolov8n.pt" # <--- NEW: Using Nano model for speed

# 4. ROBOT SETTINGS
WAKE_WORD = "hey blue"
SAFE_DISTANCE = 0.35 
ACTIVE_TIMEOUT = 60

# Global Objects
face = None
robot_hw = None
sensor = None
llm = None
yolo_model = None  # <--- NEW OBJECT
obstacle_detected = False

# ==========================================
# 🖥️  ROBOT FACE (GUI)
# ==========================================
class RobotFace:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Robot Face")
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg='black')
        self.width = self.root.winfo_screenwidth()
        self.height = self.root.winfo_screenheight()
        self.c = tk.Canvas(self.root, width=self.width, height=self.height, bg='black', highlightthickness=0)
        self.c.pack()
        
        self.eye_w = 150; self.eye_h = 200; self.gap = 100
        cx, cy = self.width / 2, self.height / 2
        self.left_eye = self.c.create_oval(cx - self.gap - self.eye_w, cy - self.eye_h/2, cx - self.gap, cy + self.eye_h/2, fill='#00FFFF', outline='')
        self.right_eye = self.c.create_oval(cx + self.gap, cy - self.eye_h/2, cx + self.gap + self.eye_w, cy + self.eye_h/2, fill='#00FFFF', outline='')
        self.state = "NEUTRAL"
        self.root.after(100, self.blink_loop) 

    def set_expression(self, expression):
        self.state = expression
        color = '#00FFFF' 
        if expression == "LISTENING": color = '#00FF00'
        elif expression == "THINKING": color = '#FF5500'
        elif expression == "SPEAKING": color = '#FFFFFF'
        try:
            self.c.itemconfig(self.left_eye, fill=color)
            self.c.itemconfig(self.right_eye, fill=color)
            self.root.update()
        except: pass

    def blink_loop(self):
        if self.state in ["NEUTRAL", "LISTENING"]:
            h, cx, cy = 10, self.width/2, self.height/2
            try:
                self.c.coords(self.left_eye, cx-self.gap-self.eye_w, cy-h, cx-self.gap, cy+h)
                self.c.coords(self.right_eye, cx+self.gap, cy-h, cx+self.gap+self.eye_w, cy+h)
                self.root.update()
                time.sleep(0.1)
                h = self.eye_h / 2
                self.c.coords(self.left_eye, cx-self.gap-self.eye_w, cy-h, cx-self.gap, cy+h)
                self.c.coords(self.right_eye, cx+self.gap, cy-h, cx+self.gap+self.eye_w, cy+h)
                self.root.update()
            except: pass
        self.root.after(random.randint(2000, 6000), self.blink_loop)

# ==========================================
# 🧠  HELPER FUNCTIONS
# ==========================================
def speak(text):
    if face: face.set_expression("SPEAKING")
    print(f"🤖 Robot: {text}")
    clean = text.replace("'", "").replace('"', "")
    subprocess.Popen(f'espeak -s 130 -v en+m3 " . . {clean}"', shell=True)
    time.sleep(len(text.split()) * 0.4) 
    if face: face.set_expression("NEUTRAL")

def capture_image(filename="view.jpg"):
    # Using libcamera (rpicam)
    subprocess.run(f"rpicam-still -o {filename} -t 100 --width 640 --height 480 -n", shell=True)
    return filename

def llm_query(prompt, system_prompt="You are a helpful robot assistant."):
    if face: face.set_expression("THINKING")
    try:
        output = llm.create_chat_completion(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150  
        )
        return output['choices'][0]['message']['content']
    except Exception as e:
        print(f"LLM Error: {e}")
        return "I am having trouble thinking."

def get_vision_description(image_path, prompt="Describe this scene."):
    try:
        with open(image_path, "rb") as img:
            b64 = base64.b64encode(img.read()).decode('utf-8')
        payload = {
            "model": "moondream", 
            "stream": False, 
            "messages": [{"role": "user", "content": prompt, "images": [b64]}]
        }
        res = requests.post(LAPTOP_URL, json=payload, timeout=60)
        return res.json()['message']['content']
    except Exception as e:
        print(f"Vision Error: {e}")
        return "I cannot see right now."

# ==========================================
# 🎮  ACTIONS
# ==========================================
def do_move(direction, duration=0.4):
    if obstacle_detected and direction == "forward":
        speak("Path blocked.")
        return
    speak(f"Moving {direction}")
    if robot_hw:
        if direction == "forward": robot_hw.forward()
        elif direction == "back": robot_hw.backward()
        elif direction == "left": robot_hw.left()
        elif direction == "right": robot_hw.right()
        time.sleep(duration)
        robot_hw.stop()

def do_see():
    speak("Let me check what is in front of me.")
    img_path = capture_image("current_view.jpg")
    desc = get_vision_description(img_path, "Describe what is directly in front of you briefly.")
    speak(f"I see {desc}")

# --- NEW YOLOv8 FIND FUNCTION ---
def do_find(target_object):
    speak(f"Looking for {target_object}")
    
    # 1. Capture Image
    img_path = capture_image("find_view.jpg")
    
    # 2. Run YOLO Inference
    if yolo_model:
        results = yolo_model(img_path, verbose=False)
        
        found = False
        location = "CENTER"
        
        # 3. Analyze Results
        for r in results:
            for box in r.boxes:
                # Get class name (e.g., 'cup', 'person')
                class_id = int(box.cls[0])
                class_name = yolo_model.names[class_id]
                confidence = float(box.conf[0])

                # Check if this is what we want (simple string matching)
                if target_object in class_name.lower() and confidence > 0.5:
                    found = True
                    
                    # Calculate Position (Left/Right/Center)
                    x1, y1, x2, y2 = box.xyxy[0]
                    center_x = (x1 + x2) / 2
                    image_width = 640
                    
                    if center_x < (image_width / 3):
                        location = "LEFT"
                    elif center_x > (image_width * 2 / 3):
                        location = "RIGHT"
                    else:
                        location = "CENTER"
                    
                    break # Stop at the first match
            if found: break
        
        # 4. Act
        if found:
            speak(f"I found the {target_object} on your {location}.")
            if location == "LEFT": do_move("left", 0.3)
            elif location == "RIGHT": do_move("right", 0.3)
            elif location == "CENTER": do_move("forward", 0.5)
        else:
            speak(f"I do not see any {target_object}.")
    else:
        speak("My vision system is not loaded.")

def do_explore():
    speak("Starting area scan.")
    observations = []
    for i in range(4):
        print(f"📸 Scanning Angle {i+1}/4...")
        img_path = capture_image(f"scan_{i}.jpg")
        desc = get_vision_description(img_path, "Describe this scene very briefly.")
        observations.append(desc)
        if i < 3:
            if robot_hw: do_move("right")
            time.sleep(0.5) 
    do_move("right")
    speak("Analyzing data.")
    summary_prompt = f"I spun around 360 degrees. Here is what I saw: {' '.join(observations)}. Summarize the room in 2 sentences."
    final_summary = llm_query(summary_prompt, "You are a robot summarizer.")
    speak(f"Report: {final_summary}")

# ==========================================
# 🎤  MAIN LOOP
# ==========================================
def main_robot_loop():
    time.sleep(2)
    rec = sr.Recognizer()
    rec.pause_threshold = 2.0
    rec.dynamic_energy_threshold = True
    
    speak("System Ready.")
    
    with sr.Microphone() as source:
        rec.adjust_for_ambient_noise(source, duration=1)
        
        while True:
            try:
                if face: face.set_expression("NEUTRAL")
                print("\n💤 Waiting for wake word ('Hey Blue')...")
                
                audio = rec.listen(source, timeout=3, phrase_time_limit=3) 
                print("\nprocessing")
                if face: face.set_expression("THINKING")
                
                text = rec.recognize_google(audio).lower()
                print(text)                
                
                if WAKE_WORD in text:
                    if face: face.set_expression("LISTENING")
                    speak("Yes?")
                    
                    last_interaction = time.time()
                    
                    while (time.time() - last_interaction) < ACTIVE_TIMEOUT:
                        try:
                            if face: face.set_expression("LISTENING")
                            audio = rec.listen(source, timeout=10) 
                            print("\nprocessing")
                            if face: face.set_expression("THINKING")
                            
                            cmd = rec.recognize_google(audio).lower()
                            
                            print(f"🗣️ User: {cmd}")
                            last_interaction = time.time()

                            if "bye" in cmd or "sleep" in cmd:
                                speak("Going to sleep.")
                                break 
                            
                            # =========================================
                            # 🚀  FAST PATH (Keywords)
                            # =========================================
                            if "explore" in cmd or "scan" in cmd:
                                do_explore()
                            elif "what do you see" in cmd or "look at this" in cmd:
                                do_see()
                            
                            # --- NEW FIND COMMAND ---
                            elif "find" in cmd or "where is" in cmd:
                                # Extract object name (e.g. "find the cup" -> "cup")
                                target = cmd.replace("find", "").replace("the", "").replace("where is", "").strip()
                                if target:
                                    do_find(target)
                                else:
                                    speak("Find what?")

                            elif "move" in cmd or "go" in cmd or "turn" in cmd:
                                found_dir = False
                                if "left" in cmd: do_move("left"); found_dir=True
                                elif "right" in cmd: do_move("right"); found_dir=True
                                elif "back" in cmd: do_move("back"); found_dir=True
                                elif "forward" in cmd: do_move("forward"); found_dir=True
                                
                                if not found_dir:
                                    speak("Which direction?")
                                    try:
                                        dir_audio = rec.listen(source, timeout=10, phrase_time_limit=3)
                                        dir_cmd = rec.recognize_google(dir_audio).lower()
                                        if "left" in dir_cmd: do_move("left")
                                        elif "right" in dir_cmd: do_move("right")
                                        elif "back" in dir_cmd: do_move("back")
                                        elif "forward" in dir_cmd: do_move("forward")
                                        else: speak("I did not hear a direction.")
                                    except: speak("Timed out.")
                                
                            # =========================================
                            # 🧠  OPTIMIZED SMART PATH (One-Shot)
                            # =========================================
                            else:
                                print("🤔 Asking Qwen to Classify OR Answer...")
                                
                                # Updated Prompt to include FIND intent
                                classify_prompt = f"""
                                User said: "{cmd}"
                                
                                Instructions:
                                1. If this is a COMMAND, return JSON:
                                   {{"intent": "MOVE", "arg": "left/right"}} 
                                   OR {{"intent": "EXPLORE"}} 
                                   OR {{"intent": "SEE"}}
                                   OR {{"intent": "FIND", "arg": "object_name"}}
                                
                                2. If this is a CHAT, return JSON:
                                   {{"intent": "CHAT", "response": "Short answer."}}
                                
                                OUTPUT JSON ONLY.
                                """
                                
                                raw_response = llm_query(classify_prompt, "You are a JSON command parser.")
                                
                                try:
                                    start_idx = raw_response.find('{')
                                    end_idx = raw_response.rfind('}') + 1
                                    json_str = raw_response[start_idx:end_idx]
                                    
                                    data = json.loads(json_str)
                                    intent = data.get("intent", "CHAT").upper()
                                    
                                    print(f"🤖 Decided: {intent}")
                                    
                                    if intent == "CHAT":
                                        reply = data.get("response", "I am not sure.")
                                        speak(reply)
                                        
                                    elif intent == "MOVE":
                                        arg = data.get("arg", "")
                                        if "left" in arg: do_move("left")
                                        elif "right" in arg: do_move("right")
                                        elif "forward" in arg: do_move("forward")
                                        elif "back" in arg: do_move("back")
                                        
                                    elif intent == "EXPLORE":
                                        do_explore()
                                        
                                    elif intent == "SEE":
                                        do_see()
                                        
                                    elif intent == "FIND":
                                        target = data.get("arg", "object")
                                        do_find(target)

                                except Exception as e:
                                    print(f"⚠️ JSON Parse Failed: {e}")
                                    fallback = llm_query(cmd, "Answer briefly.")
                                    speak(fallback)
                            
                        except sr.WaitTimeoutError: pass
                        except sr.UnknownValueError: pass
                        except Exception as e: print(e)
                    
                    speak("Sleeping.")

            except sr.WaitTimeoutError: pass
            except sr.UnknownValueError: pass
            except Exception as e: pass

def safety_monitor():
    global obstacle_detected
    while True:
        if sensor and sensor.distance < SAFE_DISTANCE:
            if not obstacle_detected:
                if robot_hw: robot_hw.stop()
                obstacle_detected = True
        else: obstacle_detected = False
        time.sleep(0.1)

# ==========================================
# 🚀  LAUNCHER
# ==========================================
if __name__ == "__main__":
    print("⏳ Initializing Hardware...")
    try: robot_hw = Robot(left=LEFT_PINS, right=RIGHT_PINS); sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIGGER_PIN)
    except: print("⚠️ HW Error")
    
    print("⏳ Initializing LLM...")
    try: llm = Llama(model_path=MODEL_PATH, n_ctx=2048, verbose=False)
    except: print("❌ LLM Error")

    # --- NEW: Initialize YOLO ---
    print("⏳ Initializing YOLOv8...")
    try:
        yolo_model = YOLO(YOLO_MODEL_PATH) 
        # This will auto-download 'yolov8n.pt' the first time
    except Exception as e: 
        print(f"❌ YOLO Error: {e}")

    threading.Thread(target=safety_monitor, daemon=True).start()
    threading.Thread(target=main_robot_loop, daemon=True).start()

    face = RobotFace()
    face.root.mainloop()
