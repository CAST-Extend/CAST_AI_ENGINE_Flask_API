# CAST-GEN AI CODE FIX ENGINE - Flask API

### Overview

This project is a Flask-based API, providing Green Deficiency code fixing by interacting with CAST Imaging and Generative AI.

### Project Structure

    CAST_AI_ENGINE_Flask_API/
    │-- api.py                # Main API entry point
    │-- app_code_fixer.py     # Module for code fixing functionality
    │-- app_imaging.py        # Module for CAST Imaging Interaction
    │-- app_llm.py            # Integration with LLM models
    │-- app_logger.py         # Logging utilities
    │-- app_mongo.py          # MongoDB database interactions
    │-- config.py             # Configuration settings
    │-- requirements.txt      # Dependencies list
    │-- utils.py              # Utility functions

### Installation

##### Prerequisites

- Python 3.x
- MongoDB 
- CAST Imaging Subscription
- Gen AI Model Subscription



### Steps

Clone the repository:

```bash
git clone <repository_url>
cd CAST_AI_ENGINE_Flask_API
```

Create a virtual environment (optional but recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Configuration

Modify config.py to update application settings such as GEN AI Model Details, CAST Imaging Details, MongoDB Details, Max Threads and Port Number.

### Usage

Running the API Server

```bash
python api.py
```

By default, the Flask server runs on http://127.0.0.1:5000/. You can modify the port in config.py if needed.



