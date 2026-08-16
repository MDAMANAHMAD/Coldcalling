import sys
import os

# Adjust path to import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_agent.agent import resolve_language

def test_language_detection():
    # 1. Hindi inputs
    hi_tests = [
        "हेलो आप कैसे हैं",
        "मुझे डिटेल्स चाहिए",
        "क्या आप मुझे बता सकते हैं"
    ]
    
    # 2. Marathi inputs
    mr_tests = [
        "मला २ बीएचके फ्लॅटची माहिती पाहिजे",
        "कल्याण ईस्ट मध्ये आहे का",
        "काही माहिती सांगा",
        "मला नको आहे",
        "पुढील नियोजन सांगा"
    ]
    
    # 3. English inputs
    en_tests = [
        "hello i am looking for a 2bhk",
        "yes please share the brochure",
        "can we schedule a site visit next saturday"
    ]
    
    print("=== TESTING RESOLVE_LANGUAGE ===")
    
    # Test Deepgram detect mock
    assert resolve_language("hello", "en-US") == "en", "Failed Deepgram English check"
    assert resolve_language("नमस्कार", "mr-IN") == "mr", "Failed Deepgram Marathi check"
    assert resolve_language("नमस्ते", "hi-IN") == "hi", "Failed Deepgram Hindi check"
    print("✓ Deepgram native language code matching passed.")
    
    # Test Local Classifier Fallback
    for text in hi_tests:
        lang = resolve_language(text, None)
        print(f"Text: '{text}' => Resolved: {lang}")
        assert lang == "hi", f"Expected hi, got {lang} for '{text}'"
        
    for text in mr_tests:
        lang = resolve_language(text, None)
        print(f"Text: '{text}' => Resolved: {lang}")
        assert lang == "mr", f"Expected mr, got {lang} for '{text}'"
        
    for text in en_tests:
        lang = resolve_language(text, None)
        print(f"Text: '{text}' => Resolved: {lang}")
        assert lang == "en", f"Expected en, got {lang} for '{text}'"
        
    print("✓ Local fallback classifier rules passed perfectly!")

if __name__ == "__main__":
    test_language_detection()
