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
  {s: "Two decks. A crossfader. EQ kills. Beat loops. A spinback on the"},
  {s: "backslash key, because of course it is. dload a this, dload b acid,"},
  {s: "deck b sync, and fade."},
  {},
  {t: "And the sync is EXACT. Not \"pretty good\". Exact.", cls: "a"},
  {},
  {s: "Real DJ software runs beat detection and guesses where the beats are."},
  {s: "It's usually right. Usually. We didn't guess, because we WROTE the song"},
  {s: "— we know the sample index of every single beat."},
  {},
  {s: "The check that runs before every deploy syncs two decks and asserts their"},
  {s: "beat phase agrees to one millionth. It does. Every time. 🎯"},
  {},
  {s: "It is a better DJ than me. It is a better DJ than you. Accept this and"},
  {s: "you'll both have a nice time."}
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
  {c: "M", d: "deck mode. two decks, a crossfader, and your keys change jobs"},
  {c: "Esc", d: "leave the prompt. now the keys are instruments. : brings it back"},
  {c: "?", d: "the whole table, whichever mode you're in"},
  {},
  {s: "You never have to memorise any of it. Press a key, it tells you what it"},
  {s: "just did. Learn by mashing. It's the correct way. 🐒"}
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
  {s: "The cheap half of it is `grade`: what's wrong with your arrangement and"},
  {s: "why, from the theory in this file, no model involved. It can't be wrong"},
  {s: "in the interesting way, because it's reading your actual song instead"},
  {s: "of vibing."}
];

/* -- help ---------------------------------------------------------------- */
C.help = [
  ["go",                    "compose a whole song, right now"],
  ["compose acid 6",        "or be specific about it"],
  ["kick x...x...x...x...", "x is a hit, . is a rest. that's the whole syntax"],
  ["bpm 150",               "faster"],
  ["grade",                 "roasted twice: how it is built, and how it sounds"],
  ["freq",                  "which track owns which frequencies, measured"],
  ["improve",               "it fixes its own mix and shows its working"],
  ["learn",                 "builds a track with you, about a minute"],
  ["why sidechain",         "what any of it actually does, in sound"],
  ["Ctrl+K",                "the palette. everything, one search away"],
  ["ask make it darker",    "the AI proposes, you press Enter"],
  ["jam on 8",               "the AI plays WITH you: one small move every 8 bars, undo vetoes"],
  ["jam style darker",       "lean the jam somewhere. it hears the grade and fixes faults first"],
  ["mix <playlist id>",      "a playlist becomes a set: beat-synced 16-bar blends, decks stay yours"],
  ["midi",                   "plug a controller in. pads are steps, the sustain pedal is play"],
  ["remix <id>",             "any public track opens as source. publish credits the original"],
  ["produce 90",             "the AI produces the track: grade, fix, regrade, until it holds up"],
  ["dream driving acid at 3am", "a sentence in, an arranged track out"],
  ["sounds",                 "the whole voice bank on one line"],
  ["real",                   "the actual Python instrument, running in this browser. beta"],
  ["key sk-ant-…",          "your own AI key. this browser only, never our server"],
  ["handle acid_mother",    "your name on the gallery"],
  ["take midnight v2",      "keep the current song server-side. it's text, it re-renders"],
  ["takes",                 "everything you kept"],
  ["playlist new warehouse","start a playlist; add <id> <song>, public <id> to share"],
  ["rec",                   "record what you hear. rec screen for video"],
  ["export",                "the whole song as a WAV"],
  ["M",                     "deck mode: dload a this · deck a sync · xf 0.5"],
  ["decks",                 "the DJ half"],
  ["keys",                  "every key, drawn on a keyboard"],
  ["ai",                    "the thing that isn't a chatbot"],
  ["share",                 "why 15KB matters more than it sounds"],
  ["free",                  "the catch (there is no catch)"],
  ["theory",                "what the machine knows"],
  ["rules",                 "every rule it grades you by, with the reason"],
  ["bands",                 "who owns which frequencies, and why"],
  ["watch",                 "nothing but the visuals, full screen. Esc comes back"],
  ["viz auto",              "the section picks the visual: builds run, drops blow out"],
  ["theme random",          "roll a palette. theme make <name> <#hex…> keeps one forever"],
  ["viz tunnel",            "the canvas. it knows where the drop is"],
  ["theme acid",            "colours. a song remembers its own"],
  ["calm",                  "dim the visuals when you want to read"],
  ["text 17",               "bigger words. text + and text - also work"],
  ["clear",                 "wipe the screen, keep the vibes"]
];

/* -- viz ----------------------------------------------------------------- */
C.viz_modes = [
  ["spectrum",  "bars, mirrored. the 1998 winamp plugin, except it can see the sub"],
  ["scope",     "the waveform, plus a lissajous loop so you can watch the bass get squarer"],
  ["tunnel",    "rings on every beat. a build makes them run; the drop blows them out"],
  ["particles", "every kick throws a handful. the hats keep them moving"],
  ["feedback",  "last frame, turned and zoomed, under this one. trails. the legal kind"],
  ["off",       "a terminal. black. you're a serious person"]
];
C.viz_status = function (s) {
  return "viz " + s.mode + " · theme " + s.theme + " · intensity " + s.intensity +
    " · decay " + s.decay + " · symmetry " + s.symmetry + (s.reduced ? " · your OS asked for less motion, so off is the default" : "");
};
C.viz_usage = "viz <mode> · viz set intensity|decay|symmetry|palette <value> · theme <name>";
C.viz_why = "it never guesses where the beat is. we wrote the song, so the canvas knows the drop is 4 bars out and starts running at it. beat detection is for people who didn't write the song.";
C.viz_set = function (k, v) { return "viz " + k + " " + v + " · saved with the song if there is one"; };
C.err_viz = function (v) { return v + ": not a mode. spectrum, scope, tunnel, particles, feedback, off. the last one is the boring one."; };
C.err_vizparam = "viz set intensity 0..2 · decay 0..1 · symmetry 1..8 · palette <theme>. out of range gets clamped, not judged.";
C.theme_set = function (t) { return "theme " + t.name + " · " + t.colors.join(" ") + " · intensity " + t.intensity + " · symmetry " + t.symmetry; };
C.err_theme = function (v) { return v + ": no such theme. type `theme` — the list is short and all of them are legal to look at."; };

/* -- errors that still teach --------------------------------------------- */
C.err_pattern = "a pattern is x for a hit and . for a rest. that's it. that's the syntax. try: kick x...x...x...x...";
C.err_cmd = function (v) {
  return v + ": nope. type help — it's short, unlike this sentence, which is now over.";
};
C.err_bpm = "bpm goes 60 to 220. techno lives at 130-150. below 100 you've made dub, above 180 you've made a mistake or gabber, and those are the same thing to some people.";
C.err_nosong = "there's no song yet. type `go` and one will appear, like magic, but with more maths.";

C.jam_usage = "jam on [bars] / jam off. the AI takes a turn every N bars while the song runs.";
C.jam_on = function (bars) { return "jam on. the AI makes one small move every " + bars + " bars, out loud, and `undo` vetoes it. a bandmate, not an oracle."; };
C.jam_needs_play = "(a jam needs a running song - press space)";
C.sounds_hint = "voice <track> <sound> swaps a circuit. track add <name> [sound] makes room for one.";

C.real_go = "loading the real one - the desktop Python instrument, whole, in this tab. ~10MB once, then it's yours.";

C.mix_usage = "mix <playlist id> · mix off. your playlists: `playlists`; public ones play too.";
C.mix_on = function (title, n) { return "mixing " + title + " - " + n + " tracks, beat-synced, 16-bar blends. grab the crossfader whenever; `mix off` makes it fully yours."; };

C.remix_usage = "remix <track id> - a public track opens as source, yours to flip. `publish` credits the original. nobody storing audio can do this.";
C.remix_on = function (t, by) { return "remixing " + t + " by " + (by || "?") + " - the whole source, playing. take it apart; `publish` credits them automatically."; };

C.produce_on = function (sc, target, rounds) { return "producing: " + sc + "/100 now, aiming for " + target + ", up to " + rounds + " rounds. every move is graded; a round that makes it worse gets reverted. one `undo` takes back the whole pass."; };
C.produce_done = function (sc, target) { return sc >= target ? "produced. " + sc + "/100 - it holds up. `publish` when you mean it." : "stopped at " + sc + "/100. the last mile is taste, and taste is yours."; };
C.dream_usage = "dream <what you want> - driving acid at 3am, warehouse dub with air in it, 150bpm anger. a sentence in, a track out.";

C.watch_on = "just the visuals now. the keys still play - Esc or a tap brings the terminal back.";
C.theme_make_usage = "theme make <name> <#hex> <#hex> [more...] - 2-6 colors, yours forever, travels with published songs.";

g.OONTZ_COPY = C;
})(window);
