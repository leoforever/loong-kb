import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from run import create_app
app = create_app()
