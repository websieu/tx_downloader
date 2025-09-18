from time import sleep
import traceback
from gologin import GoLogin

from lib.utils import GO_LOGIN_TOKEN

if __name__ == "__main__":
    try:
        gl_profile = "68a2cb0d24daa090cccefcae"
        print("start profile: "+gl_profile)
        
        gl = GoLogin({
            'token': GO_LOGIN_TOKEN,
            'profile_id': gl_profile,
            'port': 8088,

        })
        gl.start()
        sleep(5000000)
    except Exception as e:
        print("Error starting GoLogin profile:", e)
        traceback.print_exc()
        exit(1)