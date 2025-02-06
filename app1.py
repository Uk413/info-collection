import os
import json
from datetime import datetime, timedelta
from typing import Dict, Tuple

import streamlit as st
import requests
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables
load_dotenv()

# Constants
API_ENDPOINT = "https://api-dev.whereuelevate.com/internity/api/v1/drills"
DEFAULT_DRILL_PARTNER_ID = "b886470e-52ac-4d34-8621-ff3e4d8335fb"
DEFAULT_DRILL_PARTNER_NAME = "WUElev8 Innovation services private ltd"

from src.constants import DEFAULT_DRILL_INFO, CATEGORY_SUBCATEGORY_MAP
from src.utils import (
    validate_date,
    auto_correct_input,
    generate_drill_description,
    infer_subcategory,
    infer_purpose,
    infer_yes_no,
    check_for_cancellation,
)
from src.questions import HACKATHON_QUESTIONS


class StreamlitHackathonChatbot:
    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        if not self.google_api_key:
            st.error("Google API Key not found. Please set it in your .env file.")
            st.stop()
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash", temperature=0.7, api_key=self.google_api_key
        )
        self.CATEGORY_SUBCATEGORY_MAP = CATEGORY_SUBCATEGORY_MAP

    def initialize_session_state(self):
        """Initialize session state variables."""
        if "started" not in st.session_state:
            st.session_state.started = False
        if "current_question_index" not in st.session_state:
            st.session_state.current_question_index = 0
        if "hackathon_details" not in st.session_state:
            st.session_state.hackathon_details = DEFAULT_DRILL_INFO.copy()
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
        if "registration_complete" not in st.session_state:
            st.session_state.registration_complete = False

    def add_to_chat_history(self, role: str, content: str):
        """Add a message to chat history."""
        st.session_state.chat_history.append({"role": role, "content": content})

    def display_chat_history(self):
        """Display all messages in chat history."""
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    def handle_user_input(self, user_input: str, current_question: tuple) -> bool:
        """Process user input for the current question"""
        question, key = current_question

        # Add user response to chat history
        self.add_to_chat_history("user", user_input)

        # Check for cancellation
        if check_for_cancellation(user_input, self.llm):
            self.add_to_chat_history("assistant", "Registration process has been canceled.")
            st.session_state.registration_complete = True
            return False

        drill_info = st.session_state.hackathon_details

        # Process response based on question type
        if key == "drillSubCategory":
            inferred_subcategory = infer_subcategory(
                user_response=user_input,
                llm=self.llm,
                category_subcategory_map=self.CATEGORY_SUBCATEGORY_MAP,
            )
            if inferred_subcategory:
                drill_info["drillSubCategory"] = inferred_subcategory
                drill_info["drillCategory"] = self.CATEGORY_SUBCATEGORY_MAP[inferred_subcategory]
            else:
                self.add_to_chat_history("assistant", "Could not determine a valid subcategory. Please try again.")
                return False

        elif key == "drillRegistrationStartDt":
            if not validate_date(user_input):
                self.add_to_chat_history("assistant", "Invalid date format. Please use DD-MM-YYYY.")
                return False
            drill_info[key] = user_input

        elif key == "isDrillPaid":
            inferred_response = infer_yes_no(user_input, self.llm)
            if inferred_response.lower() not in ["yes", "no"]:
                self.add_to_chat_history("assistant", "Please respond with 'Yes' or 'No'.")
                return False
            drill_info[key] = inferred_response.lower() == "yes"

        elif key == "drillType":
            corrected_input = auto_correct_input(key, user_input, self.llm)
            drill_info[key] = corrected_input.title() if corrected_input.lower() in ["theme based", "product based"] else "Theme Based"

        elif key == "drillPurpose":
            inferred_purpose = infer_purpose(st.session_state, user_input, self.llm)
            drill_info[key] = inferred_purpose

        else:
            drill_info[key] = user_input

        # Explicitly update session state
        st.session_state.hackathon_details = drill_info
        return True

    def prepare_dates(self, registration_start_date: str) -> Dict[str, str]:
        """Prepare date-related fields for the payload."""
        reg_start = datetime.strptime(registration_start_date, "%d-%m-%Y")
        reg_end = reg_start + timedelta(days=15)
        phase_start = reg_end + timedelta(days=1)
        phase_end = phase_start + timedelta(days=15)

        return {
            "registration_start": reg_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "registration_end": reg_end.strftime("%Y-%m-%dT%H:%M:%S"),
            "phase_start": phase_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "phase_end": phase_end.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def submit_hackathon(self) -> bool:
        """Submit hackathon details to the API."""
        drill_info = st.session_state.hackathon_details
        dates = self.prepare_dates(drill_info["drillRegistrationStartDt"])

        # Generate description
        cost_info = "Free" if not drill_info["isDrillPaid"] else "Paid"
        drill_info["drillDescription"] = generate_drill_description(drill_info, self.llm) + f" This event is {cost_info}."

        # Prepare payload
        payload = {
            "drillName": drill_info["drillName"],
            "drillTimezone": drill_info["drillTimezone"],
            "drillRegistrationStartDt": dates["registration_start"],
            "drillRegistrationEndDt": dates["registration_end"],
            "drillStartDt": dates["phase_start"],
            "drillEndDt": dates["phase_end"],
            "drillPurpose": drill_info["drillPurpose"],
            "drillType": drill_info["drillType"],
            "isDrillPaid": drill_info["isDrillPaid"],
            "drillPhase": json.dumps({
                "type": "Single",
                "hasIdeaPhase": "",
                "isSelfPaced": False,
                "schedule": [
                    {
                        "phaseType": "HACKATHON",
                        "phaseDesc": "Hackathon Phase",
                        "dateConfirmed": True,
                        "phaseStartDt": dates["phase_start"] + ".000Z",
                        "phaseEndDt": dates["phase_end"] + ".000Z",
                        "phaseSubmissionEndDt": None,
                        "isSubmissionAllowed": False,
                        "phaseName": "Phase 1",
                        "phaseTimezone": drill_info["drillTimezone"],
                        "phaseMode": "Online",
                        "phasePosition": 0,
                    }
                ],
            }),
            "drillCategory": drill_info["drillCategory"],
            "drillSubCategory": drill_info["drillSubCategory"],
            "drillPartnerId": DEFAULT_DRILL_PARTNER_ID,
            "drillPartnerName": DEFAULT_DRILL_PARTNER_NAME,
        }

        try:
            response = requests.post(API_ENDPOINT, json=payload)
            response.raise_for_status()
            api_response = response.json()
            cust_url = api_response.get("drillCustUrl")
            if not cust_url:
                raise ValueError("API response does not contain 'drillCustUrl'.")
            drill_link = f"https://dev.whereuelevate.com/drills/{cust_url}"
            self.add_to_chat_history("assistant", f"Your event has been successfully registered! You can access it here: {drill_link}")
            return True
        except Exception as e:
            self.add_to_chat_history("assistant", f"An error occurred while submitting the hackathon: {str(e)}")
            return False

    def reset_chat(self):
        """Reset the chat to initial state."""
        st.session_state.started = False
        st.session_state.current_question_index = 0
        st.session_state.hackathon_details = DEFAULT_DRILL_INFO.copy()
        st.session_state.chat_history = []
        st.session_state.registration_complete = False

    def run(self):
        """Main run loop for the Streamlit chatbot"""
        st.title("Hackathon Event Planner")
        self.initialize_session_state()

        # Display chat history
        self.display_chat_history()

        # Start button for new registration
        if not st.session_state.started:
            if st.button("Start Registration"):
                st.session_state.started = True
                self.add_to_chat_history("assistant", "Welcome! Let's register your hackathon event.")
                self.add_to_chat_history("assistant", HACKATHON_QUESTIONS[0][0])
                st.rerun()
            return

        # Handle registration process
        if st.session_state.started and not st.session_state.registration_complete:
            current_question = HACKATHON_QUESTIONS[st.session_state.current_question_index]
            user_input = st.chat_input(f"Your response for: {current_question[0]}")

            if user_input:
                result = self.handle_user_input(user_input, current_question)
                
                if result:
                    st.session_state.current_question_index += 1
                    
                    if st.session_state.current_question_index < len(HACKATHON_QUESTIONS):
                        next_question = HACKATHON_QUESTIONS[st.session_state.current_question_index][0]
                        self.add_to_chat_history("assistant", next_question)
                        st.rerun()  # Force immediate UI update
                    else:
                        if self.submit_hackathon():
                            st.session_state.registration_complete = True
                            self.add_to_chat_history("assistant", "Registration complete! Thank you!")
                            st.rerun()  # Force final state update
                        return

        # Show reset button after completion
        if st.session_state.registration_complete:
            if st.button("Start New Registration"):
                self.reset_chat()
                st.rerun()

if __name__ == "__main__":
    chatbot = StreamlitHackathonChatbot()
    chatbot.run()
