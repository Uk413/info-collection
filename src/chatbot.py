import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import START, END, Graph
from src.constants import DEFAULT_DRILL_INFO, CATEGORY_SUBCATEGORY_MAP
from src.utils import (
    validate_date,
    auto_correct_input,
    generate_drill_description,
    infer_subcategory,
    infer_purpose,
    infer_yes_no,
    check_for_cancellation
)
from src.questions import HACKATHON_QUESTIONS
import requests

load_dotenv()

class HackathonChatbot:
    def __init__(self, google_api_key: str):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash", 
            temperature=0.7, 
            api_key=google_api_key
        )
        self.CATEGORY_SUBCATEGORY_MAP = CATEGORY_SUBCATEGORY_MAP
        self.JSON_FILE_PATH = os.path.join(os.getcwd(), 'data', 'hackathon_details.json')
        self.graph = self._build_graph()

    def _ask_questions(self, state: dict) -> dict:
        """Ask all questions defined in HACKATHON_QUESTIONS."""
        for question, key in HACKATHON_QUESTIONS:
            while True:
                user_response = input(f"AI Chatbot: {question}\nYou: ").strip()
                
                # Check if the user wants to cancel
                if check_for_cancellation(user_response, self.llm):
                    print("AI Chatbot: Registration process has been canceled.")
                    state["current_step"] = "cancel"
                    return state
                
                # Handle specific fields
                if key == "drillSubCategory":
                    inferred_subcategory = infer_subcategory(
                        user_response=user_response,
                        llm=self.llm,
                        category_subcategory_map=self.CATEGORY_SUBCATEGORY_MAP
                    )
                    if inferred_subcategory:
                        state["hackathon_details"]["drillSubCategory"] = inferred_subcategory
                        state["hackathon_details"]["drillCategory"] = self.CATEGORY_SUBCATEGORY_MAP[inferred_subcategory]
                        break
                    else:
                        print("Could not determine a valid subcategory. Please try again.")
                elif key == "drillRegistrationStartDt":
                    if not validate_date(user_response):
                        print("Invalid date format. Please use DD-MM-YYYY.")
                        continue
                    state["hackathon_details"][key] = user_response
                    break
                elif key == "isDrillPaid":
                    if user_response.lower() not in ["yes", "no"]:
                        print("Please respond with 'Yes' or 'No'.")
                        continue
                    state["hackathon_details"][key] = True if user_response.lower() == "yes" else False
                    break
                elif key == "drillType":
                    corrected_input = auto_correct_input(key, user_response, self.llm)
                    if corrected_input.lower() in ["theme based", "product based"]:
                        state["hackathon_details"][key] = corrected_input.title()
                    else:
                        state["hackathon_details"][key] = "Theme Based"
                    break
                elif key == "drillPurpose":
                    inferred_purpose = infer_purpose(state, user_response, self.llm)
                    state["hackathon_details"][key] = inferred_purpose
                    break
                else:
                    state["hackathon_details"][key] = user_response
                    break
        
        state["current_step"] = "generate_description"
        return state

    def _handle_cancellation(self, state: dict) -> dict:
        """Handle cancellation and ask if the user wants to register another event."""
        user_response = input("AI Chatbot: Would you like to register another hackathon/event? (Yes/No)\nYou: ").strip()
        inferred_response = infer_yes_no(user_response, self.llm)
        
        if inferred_response.lower() == "yes":
            state["current_step"] = "start"  # Restart the workflow
        else:
            print("Thank you for using the Hackathon Registration Chatbot! Have a great day!")
            state["current_step"] = "end"  # End the workflow
        
        return state
        
        return state

    def _generate_description(self, state: dict) -> dict:
        """
        Generate the drill description, send the data to the API, and handle the response.
        """
        drill_info = state["hackathon_details"]
        # Prepare the payload for the API
        registration_start_date = datetime.strptime(drill_info["drillRegistrationStartDt"], "%d-%m-%Y")
        registration_end_date = registration_start_date + timedelta(days=15)
        phase_start_date = registration_end_date + timedelta(days=1)
        phase_end_date = phase_start_date + timedelta(days=15)
        cost_info = "Free" if not drill_info["isDrillPaid"] else "Paid"
        drill_info["drillDescription"] = generate_drill_description(drill_info, self.llm) + f" This event is {cost_info}."
        payload = {
            "drillName": drill_info["drillName"],
            "drillTimezone": drill_info["drillTimezone"],
            "drillRegistrationStartDt": registration_start_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "drillRegistrationEndDt": registration_end_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "drillStartDt": phase_start_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "drillEndDt": phase_end_date.strftime("%Y-%m-%dT%H:%M:%S"),
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
                        "phaseStartDt": phase_start_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "phaseEndDt": phase_end_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "phaseSubmissionEndDt": None,
                        "isSubmissionAllowed": False,
                        "phaseName": "Phase 1",
                        "phaseTimezone": drill_info["drillTimezone"],
                        "phaseMode": "Online",
                        "phasePosition": 0
                    }
                ]
            }),
            "drillCategory": drill_info["drillCategory"],
            "drillSubCategory": drill_info["drillSubCategory"],
            "drillPartnerId": "b886470e-52ac-4d34-8621-ff3e4d8335fb",
            "drillPartnerName": "WUElev8 Innovation services private ltd"
        }
        # Send the payload to the API endpoint
        api_url = "https://api-dev.whereuelevate.com/internity/api/v1/drills"  # Replace with the actual API URL
        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
            api_response = response.json()
            # Extract the custom URL from the API response
            cust_url = api_response.get("drillCustUrl")
            if not cust_url:
                raise ValueError("API response does not contain 'drillCustUrl'.")
            # Construct the link for the user
            drill_link = f"https://dev.whereuelevate.com/drills/{cust_url}"
            print(f"Your event has been successfully registered! You can access it here: {drill_link}")
        except requests.exceptions.RequestException as e:
            print(f"An error occurred while communicating with the API: {str(e)}")
            state["current_step"] = "cancel"
            return state
        
        state["current_step"] = "end"
        return state

    def _build_graph(self) -> Graph:
        """
        Build the LangGraph workflow for the Hackathon Chatbot.
        """
        graph = Graph()
        # Add nodes for the main workflow
        graph.add_node("ask_questions", self._ask_questions)
        graph.add_node("generate_description", self._generate_description)
        # Add a node for handling cancellation
        graph.add_node("cancel", self._handle_cancellation)
        # Define edges for the workflow
        graph.add_edge(START, "ask_questions")  # Start with asking questions
        # After asking questions, decide whether to generate a description or handle cancellation
        def decide_next_step(state: dict):
            if state["current_step"] == "cancel":
                return "cancel"
            return "generate_description"
        graph.add_conditional_edges("ask_questions", decide_next_step)
        # After generating the description, end the workflow
        graph.add_edge("generate_description", END)
        # After handling cancellation, decide whether to restart or end
        def decide_after_cancellation(state: dict):
            if state["current_step"] == "start":
                return START  # Restart the workflow
            return END  # End the workflow
        graph.add_conditional_edges("cancel", decide_after_cancellation)
        return graph.compile()

    def run(self):
        """
        Run the LangGraph workflow.
        """
        while True:
            try:
                # Initialize the state for the current hackathon registration
                initial_state = self._initialize_state()
                # Execute the workflow
                final_state = self.graph.invoke(initial_state)
                # If the workflow ends naturally (not canceled), ask to register another event
                if final_state["current_step"] == "end":
                    user_response = input("AI Chatbot: Would you like to register another hackathon/event? (Yes/No)\nYou: ").strip()
                    inferred_response = infer_yes_no(user_response, self.llm)
                    if inferred_response.lower() == "yes":
                        continue  # Restart the workflow
                    else:
                        print("Thank you for using the Hackathon Registration Chatbot! Have a great day!")
                        break  # Exit the loop
            except Exception as e:
                # Handle errors gracefully
                print(f"An error occurred: {str(e)}. Please try again or contact support.")
                continue
            
    def _initialize_state(self):
        """Initialize the state for a new hackathon registration."""
        return {"hackathon_details": DEFAULT_DRILL_INFO.copy(), "current_step": "start"}