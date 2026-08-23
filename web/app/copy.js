/* The words, oontz.sh edition.
 *
 * VOICE — this is the same product as oontz.music with the tie off and the
 * lights down. .music is the pitch; .sh is the 4am voice note from the person
 * who actually built it. Rude, fast, funny, and — this is the part that matters
 * — never dumber. Every joke here still ships a fact.
 *
 * THE RULES, because "be funny" is not a brief:
 *   1. A joke must carry information. If you delete the joke and lose nothing,
 *      the joke was decoration. Cut it.
 *   2. Punch at the software, the industry, and the author. Never at the user.
 *      The user is having a hard enough time; they opened a terminal to make
 *      music.
 *   3. Swearing is seasoning. Techno is not a polite genre and this is not a
 *      polite tool, but nothing here needs to be filthy to be funny.
 *   4. Deadpan beats zany. The funniest thing on this page is that it is all
 *      completely true.
 *   5. Specific > general. "a 12-bar section" is funnier than "a weird section"
 *      because it is a real crime with real victims.
 */
(function (g) {
"use strict";

var C = {};

C.tagline = "you opened a terminal to make dance music. respect. 🫡";

C.boot = [
  "Somewhere a UX designer just felt a chill and doesn't know why.",
  "No mouse. No rectangles. No 4GB download. No 'welcome to your journey'."
];

C.menu = [
  ["go",      "make a whole song. right now. one command. no notes app required"],
  ["what",    "what is happening to me"],
  ["decks",   "two turntables and a keyboard, obviously"],
  ["keys",    "the entire instrument, drawn on your actual keyboard"],
  ["help",    "everything. it's a lot. sorry. not sorry"]
];

/* -- what ---------------------------------------------------------------- */
C.what = [
  {t: "Right. So. 🎛️", cls: "b"},
  {},
  {s: "This is a drum machine that lives in a command line, because someone"},
  {s: "looked at a $600 DAW and thought \"what if this, but you could grep it\"."},
  {},
  {s: "That someone was me. I regret nothing."},
  {},
  {c: "kick x...x...x...x...", d: "four to the floor. you're a producer now. update your bio"},
  {c: "hat  ..x...x...x...x.", d: "hats between the kicks. this is the entire trick"},
  {c: "bass a1 . a1~ c2",      d: "~ slides. that's a 303. that's THE sound. yes, that one"},
  {},
  {s: "Nothing is sampled. Every kick is a sine wave being emotionally"},
  {s: "manipulated — pitch falls 150Hz to 50Hz in 40ms, then gets saturated"},
  {s: "until it clips politely. Every hat is white noise that got sent through"},
  {s: "an 8kHz highpass and told to be brief. 🥁"},
  {},
  {s: "It is arithmetic. It is arithmetic all the way down. It slaps anyway."}
];

/* -- go ------------------------------------------------------------------ */
C.go = [
  {t: "One command. A whole song. Not a loop — a SONG. 🎹", cls: "b"},
  {},
  {c: "compose hardtechno 5", d: "five minutes. intro, builds, drops, breaks, outro"},
  {},
  {s: "It doesn't shuffle patterns and call it an arrangement. It walks an"},
  {s: "energy curve, picks a shape that real records actually use, and develops"},
  {s: "ONE motif across the whole thing — so the bassline in the drop is"},
  {s: "recognisably the one from the intro, grown up and angry."},
  {},
  {s: "That last bit is the difference between a song and eight unrelated loops"},
  {s: "in a trenchcoat. 🧥"}
];

/* -- theory -------------------------------------------------------------- */
C.theory = [
  {t: "It will grade your track. Out of 100. To your face. 📋", cls: "b"},
  {},
  {c: "grade", d: "brace yourself"},
  {},
  {s: "There's a music theory engine in here and it has OPINIONS:"},
  {},
  {s: "  - the drop goes 20-40% in. earlier and there's no tension to release,"},
  {s: "    you've just started shouting at a stranger"},
  {s: "  - sections come in multiples of 8. a 12-bar section is a hate crime"},
  {s: "    against everyone counting on the dancefloor"},
  {s: "  - 16-32 bars of plain intro or no DJ can mix into your track and it"},
  {s: "    dies alone in a folder called 'ideas'"},
  {s: "  - the kick owns 40-90Hz. ALONE. put your sub there too and congrats,"},
  {s: "    you've invented mud 🟤"},
  {},
  {s: "A properly built track scores in the nineties. A pile of loops with a"},
  {s: "12-bar section scores zero and gets told, specifically, why."},
  {},
  {s: "This is the difference between a generator you have to trust and one you"},
  {s: "can pick a fight with. Pick the fight. It's usually right, which is worse."}
];

/* -- decks --------------------------------------------------------------- */
C.decks = [
  {t: "Press M. Now you're a DJ. 🎧", cls: "b"},
  {},
  {s: "Two decks. A crossfader. EQ kills. Loop rolls. A spinback on the"},
  {s: "backslash key, because of course it is."},
  {},
  {t: "And the sync is EXACT. Not \"pretty good\". Exact.", cls: "a"},
  {},
  {s: "Real DJ software runs beat detection and guesses where the beats are."},
  {s: "It's usually right. Usually. We didn't guess, because we WROTE the song"},
  {s: "— we know the sample index of every single beat."},
  {},
  {s: "Measured drift between two synced decks over 23 seconds: 0.0000. 🎯"},
  {},
  {s: "It'll also tell you which of your tracks mix together, in what key, and"},
  {s: "why. It is a better DJ than me. It is a better DJ than you. Accept this"},
  {s: "and you'll both have a nice time."}
];

/* -- free ---------------------------------------------------------------- */
C.free = [
  {t: "It's free. Actually free. Suspiciously free. 💸", cls: "b"},
  {},
  {s: "No Pro tier. No credits. No \"unlock the good reverb for $9/month\"."},
  {s: "No email drip where I pretend we're friends now. No funnel. I'm not"},
  {s: "building a funnel, I'm building a drum machine."},
  {},
  {s: "Here's the actual reason, and it's not generosity:"},
  {},
  {s: "The audio is computed in YOUR browser on YOUR CPU. There's no render"},
  {s: "farm. When you make a five-minute banger at 3am it costs me precisely"},
  {s: "nothing, because I am not involved. You're expensive to yourself. 🔥"},
  {},
  {s: "And a whole track saves as 15 kilobytes of text. Not the audio — the"},
  {s: "SONG. A thousand of them is fifteen megabytes. That's one photo of a"},
  {s: "sandwich. I can host everyone's music forever for less than a coffee."},
  {},
  {s: "An account is an email. It buys you: songs saved, and the button that"},
  {s: "makes them public. That's it. That's the whole business model. There"},
  {s: "isn't one."}
];

/* -- share --------------------------------------------------------------- */
C.share = [
  {t: "When you share a track, you're not sending audio. 📄", cls: "b"},
  {},
  {s: "You're sending the SOURCE. 15KB. Every pattern, every filter sweep,"},
  {s: "the whole arrangement, in text."},
  {},
  {s: "Which means whoever opens it doesn't just hear your drop. They can see"},
  {s: "exactly how you built it, change one number, and hear that instead."},
  {},
  {t: "You share the recipe, not the cake. 🍰", cls: "a2"},
  {},
  {s: "Every track on this site is a playable, editable, steal-able preset."},
  {s: "Yes, people can nick your bassline. Good. That's how house music"},
  {s: "happened. That's how ALL of it happened. 🏴‍☠️"}
];

/* -- keys ---------------------------------------------------------------- */
C.keys = [
  {t: "Your keyboard is the controller. All of it. 🎹", cls: "b"},
  {},
  {c: "qwertyui asdfghjk", d: "sixteen step pads. two rows. like actual hardware"},
  {c: "1-8", d: "pick a track"},
  {c: "[ ]  (hold)", d: "filter sweep. this is the fun one. hold it"},
  {c: "/    (hold)", d: "loop roll. THE live move. hold it and look smug"},
  {c: "\\", d: "spinback. no notes. perfect key. chef's kiss"},
  {c: "space", d: "you know what space does"},
  {c: "R", d: "record. captures exactly what you heard, effects and all"},
  {c: "?", d: "draws your entire keyboard on screen, lit up by what each key does"},
  {},
  {s: "You never have to memorise any of it. The legend is always on screen and"},
  {s: "it changes depending on what you're touching. Press a key, it tells you"},
  {s: "what it just did. Learn by mashing. It's the correct way. 🐒"}
];

/* -- ai ------------------------------------------------------------------ */
C.ai = [
  {t: "There's an AI in here and it is not a chatbot. 🤖", cls: "b"},
  {},
  {c: "ask make it darker and half time", d: "then hit Enter to accept"},
  {},
  {s: "It NEVER touches your track on its own. It proposes commands — the same"},
  {s: "commands you could've typed — and you press Enter or you don't."},
  {},
  {s: "Which means everything it does lands in undo, shows up in your song"},
  {s: "file, and can be read back later. No black box. No \"the AI did something"},
  {s: "and now the snare is gone and nobody knows where\". 🫥"},
  {},
  {s: "It also just sits there telling you useful things for free: what's"},
  {s: "playing, what's wrong with it, and which key to press next. Most of that"},
  {s: "costs nothing and can't be wrong, because it's reading your actual song"},
  {s: "instead of vibing."}
];

/* -- help ---------------------------------------------------------------- */
C.help = [
  ["go",                    "compose a whole song, right now"],
  ["compose acid 6",        "or be specific about it"],
  ["kick x...x...x...x...", "x is a hit, . is a rest. that's the whole syntax"],
  ["bpm 150",               "faster"],
  ["grade",                 "get roasted by music theory"],
  ["decks",                 "the DJ half"],
  ["keys",                  "every key, drawn on a keyboard"],
  ["ai",                    "the thing that isn't a chatbot"],
  ["share",                 "why 15KB matters more than it sounds"],
  ["free",                  "the catch (there is no catch)"],
  ["theory",                "what the machine knows"],
  ["clear",                 "wipe the screen, keep the vibes"]
];

/* -- errors that still teach --------------------------------------------- */
C.err_pattern = "a pattern is x for a hit and . for a rest. that's it. that's the syntax. try: kick x...x...x...x...";
C.err_cmd = function (v) {
  return v + ": nope. type help — it's short, unlike this sentence, which is now over.";
};
C.err_bpm = "bpm goes 60 to 220. techno lives at 130-150. below 100 you've made dub, above 180 you've made a mistake or gabber, and those are the same thing to some people.";
C.err_nosong = "there's no song yet. type `go` and one will appear, like magic, but with more maths.";

g.OONTZ_COPY = C;
})(window);
