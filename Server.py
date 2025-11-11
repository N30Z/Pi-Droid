import cam 


wrong_code = "Falscher Code. Bitte erneut versuchen."
swipe_text = "Zum Entsperren wischen"


def get_timeout():
    text = cam.get_text('Info_text')  # uses default timeout internally
    text = ''.join(ch for ch in (text or '') if ch.isdigit())    # keep only numeric digits
    if text:
        return int(text)
    
def wrong_code_detected():
    if cam.get_text('Info_text') == wrong_code:
        return True
    else:
        return False
    
def check_swipe():
    if cam.check('Swipe', threshold=0.8) == swipe_text:
        return True
    else:
        return False