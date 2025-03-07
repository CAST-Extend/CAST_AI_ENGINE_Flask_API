import json
import logging
import time
import requests
import tiktoken

from flask import Config as FlaskConfig
from app_logger import AppLogger

class AppLLM:
    def __init__(self, app_logger: AppLogger,  config: FlaskConfig):
        self.model_name = config["MODEL_NAME"]
        self.model_version = config["MODEL_VERSION"] # UNUSED
        self.model_url = config["MODEL_URL"]
        self.model_max_input_tokens = config["MODEL_MAX_INPUT_TOKENS"]
        self.model_max_output_tokens = config["MODEL_MAX_OUTPUT_TOKENS"]
        self.model_invocation_delay = config["MODEL_INVOCATION_DELAY_IN_SECONDS"]
        self.headers = { "Authorization": f"Bearer {config["MODEL_API_KEY"]}", "Content-Type": "application/json" }
        self.app_logger = app_logger
        self.first_prompt = True
        try:
            # Try to retrieve the appropriate token encoding based on the AI model name.
            # Different models may use different tokenization methods.
            self.encoding = tiktoken.encoding_for_model(self.model_name)
            print(f"Using encoding for {self.model_name}")
        except KeyError:
            # If the model name is not recognized (causing a KeyError), fall back to a default encoding.
            # 'cl100k_base' is a common fallback for models that do not have a specific encoding.
            self.encoding = tiktoken.get_encoding("cl100k_base")
            print(f"Using fallback encoding 'cl100k_base'")

    # private methods
    def count_tokens(self, prompt):
        try:
            """
            Counts the number of tokens in the given prompt using the token encoding for the specified AI model.

            Parameters:
            ai_model_name (str): The name of the AI model, used to select the appropriate token encoding.
            prompt (str): The input text for which tokens will be counted.

            Returns:
            int: The number of tokens in the prompt.
            """
            # Encode the prompt using the selected encoding, which converts the text into tokens.
            tokens = self.encoding.encode(prompt)

            # Return the total number of tokens in the prompt.
            return len(tokens)
        except Exception as e:
            # Catch and print any errors that occur.
            print(f"An error occurred: {e}")
            self.app_logger.log_error("count_tokens", e)

    def ask_ai_model(
        self,
        prompt_content,
        json_resp,
        max_tokens,
        ObjectID=None,
    ):
        # REM-DMA: I understand the LLM is rate limited
        # REM-DMA: typically, if a request is denied because of rate-limitation, the HTTP status code should be 429 (Too Many Requests)
        # REM-DMA: in which case a "Retry-After" header may be provided indicating when a new request can be issued
        # REM-DMA: "Retry-After" can contain a date/time or a delay in seconds
        # REM-DMA: see https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Retry-After
        # REM-DMA: maybe it would be interesting to use that info, if available, to optimize throughput?
        # REM-DMA: the idea would be to remove all systematic calls to "time.sleep"
        # REM-DMA: and only sleep when the limited has been exceeded

        if self.first_prompt:
            self.first_prompt = False
        else:
            # Delay for model invocation
            time.sleep(self.model_invocation_delay)  

        MAX_RETRIES = 3

        try:
            """
            Sends a prompt to the AI model and retrieves a valid JSON response.
            Retries the request if an invalid JSON is received.

            Parameters:
            prompt_content (str): prompt to send to the AI model.
            max_tokens (int): The maximum number of tokens the AI model can generate.

            Returns:
            dict or None: The JSON response from the AI model if valid, otherwise None.
            """

            # REM-DMA: the prompt contains code, and the code could contain valid '\\n' or '\\"' or '\\\\' sequences
            # REM_DMA: seems risky... replacing escape sequences in the prompt should be done by the caller,
            # REM_DMA: only the caller knows how the prompt was constructed and where it is safe to unescape characters
            # prompt_content = (prompt_content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\"))

            print(f"\n processing objectID - {ObjectID}.........")

            # with open(f"prompt_content_for_objectID_{ObjectID}.txt", "w") as f:
            #     f.write(prompt_content)
            #     prompt_content_token = self.count_tokens(str(prompt_content))
            #     print("prompt content token: ",{prompt_content_token})

            messages = [{"role": "user", "content": prompt_content}]

            # Prepare the payload for the AI API
            payload = { "model": self.model_name, "messages": messages, "temperature": 0 }

            # with open(f"payload_{ObjectID}.json", "w") as f:
            #     json.dump(payload, f, indent=4)

            # Loop for retrying the request in case of errors or invalid JSON.
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    # Send the request to the AI model and get the completion response.
                    response = requests.post(self.model_url, headers=self.headers, json=payload)
                    response.raise_for_status()  # Raise an error for bad responses

                    # Extract the AI model's response content (text) from the first choice.
                    response_content = response.text

                    logging.info(f"AI Response (Attempt {attempt}): {response_content}")

                    # Try to parse the AI response as JSON.
                    try:
                        response_json = json.loads(response_content)

                        ai_response = response_json["choices"][0]["message"]["content"]

                        # with open(f"AI_Response_for_ObjectID_{ObjectID}.json", "w") as f:
                        #     json.dump(response_json, f, indent=4)
                        #     json.dump(ai_response, f, indent=4)
                        #     Ai_Response_content_token = count_chatgpt_tokens(ai_model_name, str(response_content))
                        #     print("AI Response content token: ",{Ai_Response_content_token})


                        ai_response = response_json["choices"][0]["message"]["content"]
                        ai_response = json.loads(ai_response)  # Successfully parsed JSON, return it.

                        print(f"processed objectID - {ObjectID}.")

                        return ai_response, "success"
                    except json.JSONDecodeError as e:
                        # Log the JSON parsing error and prepare for retry if needed.
                        logging.error(f"JSON decoding failed on attempt {attempt}: {e}")

                        if attempt < MAX_RETRIES:
                            # If attempts remain, wait for a delay before retrying.
                            logging.info(f"Retrying AI request in {self.model_invocation_delay} seconds...")
                            time.sleep(self.model_invocation_delay)

                            prompt_content = (
                                f"The following text is not a valid JSON string:\n```{ai_response}```\n"
                                f"When trying to parse it with json.loads() in Python script, one gets the following error:\n```{e}```\n"
                                f"It should match the following structure:\n```{json_resp}```\n"
                                f"\nMake sure your response is a valid JSON string.\nRespond only the JSON string, and only the JSON string. "
                                f"Do not enclose the JSON string in triple quotes, backslashes, ... Do not add comments outside of the JSON structure.\n"
                            )

                            # prompt_content = (prompt_content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\"))

                            messages = [{"role": "user", "content": prompt_content}]
                            # Prepare the payload for the AI API
                            payload = { "model": self.model_name, "messages": messages, "temperature": 0 }

                        else:
                            # If max retries reached, log an error and return None.
                            logging.error("Max retries reached. Failed to obtain valid JSON from AI.")
                            return None, "Max retries reached! Failed to obtain valid JSON from AI. Please Resend the request..."

                except Exception as e:
                    # Log any general errors during the request, and retry if possible.
                    print(f"Error during AI model completion for the objectID-{ObjectID}:  {e}")
                    return None, f"{e}. Please Resend the request..."

            # Return None if all attempts fail.
            return None, "AI Model failed to fix the code. Please Resend the request..."
        except Exception as e:
            # Catch and print any errors that occur.
            print(f"An error occurred: {e}")
            self.app_logger.log_error(e, "ask_ai_model")
            return None, f"{e}. Please Resend the request..."
