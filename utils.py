from datetime import datetime
import re
import secrets
import string

from app_logger import AppLogger

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def generate_unique_alphanumeric(app_logger: AppLogger, length = 24):
    try:
        characters = string.ascii_letters + string.digits
        return "".join(secrets.choice(characters) for _ in range(length))
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        app_logger.log_error("generate_unique_alphanumeric", e)

# REM-DMA: unused, should be removed?
# def fix_common_json_issues(app_logger: AppLogger, json_string):
#     try:
#         """
#         Fix common JSON formatting issues such as unescaped newlines and quotes.

#         Parameters:
#         json_string (str): The input JSON string that may contain formatting issues.

#         Returns:
#         str: A JSON string with fixed formatting issues.
#         """
#         # Replace actual newlines with escaped newlines (\n) to prevent JSON parsing errors.
#         # JSON requires newlines to be escaped, but they might be present as actual newlines in the input.
#         json_string = json_string.replace("\n", "\\n")

#         # Use a regular expression to escape double quotes that are not already escaped.
#         # The regex (?<!\\)" looks for double quotes that are not preceded by a backslash, meaning they are not escaped.
#         # We replace these unescaped quotes with an escaped version (\").
#         json_string = re.sub(r'(?<!\\)"', r"\"", json_string)

#         # Return the modified JSON string with fixed formatting.
#         return json_string
#     except Exception as e:
#         # Catch and print any errors that occur.
#         print(f"An error occurred: {e}")
#         app_logger.log_error("fix_common_json_issues", e)

def replace_lines(app_logger: AppLogger, lines, replacements):
    try:
        # Make a copy of the original lines to work with
        modified_lines = lines[:]
        
        # Sort the replacements by starting line in reverse order
        # to avoid shifting issues when replacing lines
        for (start, end), replacement_lines in sorted(replacements.items(), reverse=True):
            modified_lines[int(start)-1:int(end)] = replacement_lines
        
        return modified_lines
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        app_logger.log_error("replace_lines", e)
