#%%
#!pip install nest-asyncio
# import nest_asyncio
# nest_asyncio.apply()
#%%
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from device import *
from device_manager import *

import asyncio

#%%
import logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# 2. Configure logging to print explicitly to the notebook cell stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
# %%
dm = DeviceManager()
# %%
d = dm.register_device('192.168.2.102')
# %%
await dm.start_all()
# %%
dm.get_all_states()
# %%
await dm.stop_all()
# %%
