import os, sys

# Let's inspect oasis default platform or environment attributes
import oasis
sim_dir = 'backend/uploads/simulations/sim_083f8cc0d041'
db_path = os.path.abspath(os.path.join(sim_dir, 'twitter_simulation.db'))

# Check platform attributes if any
from oasis.social_platform.platform import Platform
print('Platform class attrs:', dir(Platform))
