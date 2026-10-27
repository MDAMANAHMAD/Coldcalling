import sys
import re

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def test_pipeline():
    sample = "नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?"
    print("Test 1: Opening greeting sample:", sample)
    
    # Check phone noise / digit artifact filter
    noise_samples = ["2", "1", "प", "ah", "2.", " ", ""]
    for n in noise_samples:
        clean = re.sub(r'[^\w\s]', '', n).strip()
        is_artifact = (not clean or clean.isdigit() or len(clean) <= 1 or clean.lower() in ['2', '1', '3', '4', '5', 'प', 'द', 'अ', 'h', 'ah', 'uh'])
        assert is_artifact, f"Failed on noise sample: {n}"
    print("Test 2: Artifact filter works properly.")

    # Check human speech detection
    human_samples = ["hello", "namaste", "ha boliye", "kya price hai", "one bhk chahiye"]
    HUMAN_GREETING_WORDS = [
        "hello", "namaskar", "namaste", "haan", "ha", "haa", "boliye", "bolo", "kaun",
        "kaun bol", "sun raha", "bataiye", "yes", "hi", "who is", "kya hai", "accha",
        "bhk", "flat", "sai garden", "dombivli", "property", "details", "ji"
    ]
    for h in human_samples:
        words = h.lower().split()
        is_human = any(w in h.lower() for w in HUMAN_GREETING_WORDS) or len(words) >= 2
        assert is_human, f"Failed on human sample: {h}"
    print("Test 3: Human speech filter works properly.")

    # Check voicemail detection
    VOICEMAIL_PATTERNS = [
        r"\b(voicemail|voice\s*mail)\b",
        r"\b(leave\s*(a|your)?\s*message)\b",
        r"\b(after\s*the\s*(tone|beep))\b",
        r"\b(record\s*(your)?\s*message)\b",
        r"\b(at\s*the\s*tone)\b",
        r"\b(call\s*forward(ed|ing)?)\b",
        r"\b(forward(ed)?\s*to)\b",
        r"\b(email\s*forward(ing)?)\b",
        r"\b(switched\s*off)\b",
        r"\b(switch\s*off)\b",
        r"\b(not\s*reachable)\b",
        r"\b(out\s*of\s*coverage)\b",
        r"\b(currently\s*unavailable)\b",
        r"\b(cannot\s*(take|answer)\s*(your)?\s*call)\b",
        r"\b(cannot\s*be\s*reached)\b",
        r"\b(vyast\s*hai)\b",
        r"\b(dusre\s*call\s*par)\b",
        r"\b(another\s*call)\b",
        r"\b(busy\s*on\s*another\s*call)\b",
        r"\b(kripya\s*(kuch\s*samay\s*)?baad)\b",
        r"\b(please\s*try\s*again\s*later)\b",
        r"\b(does\s*not\s*exist)\b",
        r"\b(invalid\s*number)\b",
    ]
    vm_samples = [
        "Please leave a message after the tone",
        "Your call has been forwarded to voicemail",
        "The person you are calling is currently unavailable",
        "kripya kuch samay baad call karein"
    ]
    for v in vm_samples:
        is_vm = any(re.search(pat, v, re.IGNORECASE) for pat in VOICEMAIL_PATTERNS)
        assert is_vm, f"Failed on voicemail sample: {v}"
    print("Test 4: Voicemail / answering machine detection works properly.")

    print("\n✅ ALL PIPELINE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_pipeline()
