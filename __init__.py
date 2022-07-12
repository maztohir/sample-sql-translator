import os
import sys
  
# directory reach
directory = os.path.dirname(os.path.abspath(__file__))
  
# setting path
sys.path.append(directory)

sys.setrecursionlimit(1500)