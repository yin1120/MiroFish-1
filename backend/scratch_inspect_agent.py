import sys

sys.stdout.reconfigure(encoding='utf-8')

# Check how SocialAgent initializes its system_message and how step/astep is called
import oasis.social_agent.agent
import inspect

print("SocialAgent class hierarchy:", oasis.social_agent.agent.SocialAgent.__mro__)
print("\nSocialAgent.__init__ source snippet:")
lines, start = inspect.getsourcelines(oasis.social_agent.agent.SocialAgent.__init__)
for l in lines[:40]:
    print(l, end='')
