import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv

load_dotenv()

def get_llm():
    """Create and return a ChatGoogleGenerativeAI instance with proper authentication."""
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set")
        
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0.7,
        google_api_key=google_api_key  # Explicitly pass the API key
    )

llm = get_llm()

def validate_date(date_str: str) -> bool:
    """Validate date format (DD-MM-YYYY)."""
    pattern = r"^(0[1-9]|[12][0-9]|3[01])-(0[1-9]|1[0-2])-\d{4}$"
    return re.match(pattern, date_str) is not None

def auto_correct_input(field_name: str, user_input: str, llm=None) -> str:

    """Use LLM to auto-correct typos in user input."""
    if llm is None:
        llm = get_llm()

    correction_prompt = f"""
    The user entered '{user_input}' for the field '{field_name}'. 
    If there are any typos or errors in the input, correct it and provide the most likely intended value.
    If the input is already correct, return it as-is.
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", correction_prompt),
        ("human", "Please provide the corrected value.")
    ])
    response = (prompt_template | llm).invoke({})
    return response.content.strip()

def generate_drill_description(drill_info: dict, llm=None) -> str:
    """Generate a short description for the event."""
    if llm is None:
        llm = get_llm()
    description_prompt = f"""
    Generate a short description for the following event:
    Name: {drill_info["drillName"]}
    Type: {drill_info["drillType"]}
    Purpose: {drill_info["drillPurpose"]}
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", description_prompt),
        ("human", "Please generate the description based on the above details.")
    ])
    response = (prompt_template | llm).invoke({})
    return response.content.strip()

def infer_purpose(state: dict, user_response: str, llm=None) -> str:
    """Use LLM to infer the purpose of the event."""
    if llm is None:
        llm = get_llm()
    subcategory = state["hackathon_details"].get("drillSubCategory", "").upper()
    prompt = f"""
    Based on the drill subcategory '{subcategory}' and the user input: '{user_response}',
    determine the most likely purpose of the event.
    The possible purposes are 'Innovation' or 'Hiring'.
    If the input strongly suggests one of these purposes, return it.
    Otherwise, default to 'Innovation'.
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt),
        ("human", "Provide the inferred purpose.")
    ])
    response = (prompt_template | llm).invoke({})
    inferred_purpose = response.content.strip().capitalize()
    return inferred_purpose if inferred_purpose in ["Innovation", "Hiring"] else "Innovation"

def infer_subcategory(user_response: str, category_subcategory_map: dict, llm=None) -> str:
    if llm is None:
        llm = get_llm()
    """Use LLM to infer the most relevant subcategory."""
    valid_subcategories = list(category_subcategory_map.keys())
    prompt = f"""
    Given the user input: '{user_response}', determine the most relevant subcategory from the following list:
    {valid_subcategories}.
    If no clear match is found, return an empty string.
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt),
        ("human", "Provide the inferred subcategory.")
    ])
    response = (prompt_template | llm).invoke({})
    inferred_subcategory = response.content.strip().upper()
    return inferred_subcategory if inferred_subcategory in category_subcategory_map else ""

def infer_yes_no(user_response: str, llm=None) -> str:
    """Use LLM to infer whether the user's response is 'Yes' or 'No'."""
    if llm is None:
        llm = get_llm()
    prompt = f"""
    Given the user input: '{user_response}', determine whether the response indicates 'Yes' or 'No'.
    Return 'Yes' if the input strongly suggests affirmation, otherwise return 'No'.
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt),
        ("human", "Provide the inferred response.")
    ])
    response = (prompt_template | llm).invoke({})
    inferred_response = response.content.strip().capitalize()
    return inferred_response if inferred_response in ["Yes", "No"] else "No"

def check_for_cancellation(user_response: str, llm=None) -> bool:
    if llm is None:
        llm = get_llm()
    """Use LLM to infer if the user wants to cancel the registration process."""
    prompt = f"""
    Given the user input: '{user_response}', determine whether the user wants to cancel the registration process.
    Return 'True' if the input strongly suggests cancellation (e.g., 'cancel', 'stop', 'don't want to proceed'), otherwise return 'False'.
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt),
        ("human", "Provide the inferred response.")
    ])
    response = (prompt_template | llm).invoke({})
    inferred_response = response.content.strip().capitalize()
    return inferred_response == "True"