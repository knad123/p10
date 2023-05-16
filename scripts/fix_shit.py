import re
import os
dir = "temporal_demands"

for demand in [os.path.join(dir, file) for file in os.listdir(dir)]:
    with open(demand, "r") as f:
        content = f.read()
        content_fixed = re.sub("__+", "_", content)
    with open(demand, "w") as f:
        f.write(content_fixed)