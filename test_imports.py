import sys
import traceback

try:
    from app.models import *
    print("Models imported successfully!")
except Exception as e:
    print("Import error detected:")
    traceback.print_exc()
