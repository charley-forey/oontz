/* The words.
 *
 * Kept in one file, apart from the machinery, because copy gets rewritten twenty
 * times more often than code does and it should not require touching either.
 *
 * VOICE — oontz.music (this side): dry, confident, self-aware. It is a product
 * page pretending to be a terminal, and it knows that, and it is not smug about
 * it. Jokes carry information; if a line is funny but teaches nothing, it is cut.
 * Every claim has a number behind it. Short sentences. No exclamation marks
 * except where something genuinely surprising just happened.
 *
 * The arc, in order, because a landing page is a story and this is its plot:
 *   1. HOOK      it makes noise before it explains itself
 *   2. PROBLEM   why music software feels bad
 *   3. INSIGHT   a song is text — and here is the number that proves it matters
 *   4. PROOF     you already changed a pattern and heard it, ten seconds ago
 *   5. STAKES    it is free, and here is the real reason it can be
 *   6. INVITE    go make something
 */
(function (g) {
"use strict";

var C = {};

C.tagline = "techno from a command line.";

C.boot = [
  "Every sound is synthesized from arithmetic. No samples, no plugins, no login.",
  "A whole track is a text file. That turns out to matter more than it sounds."
];

C.menu = [
  ["demo",  "hear it. right now, in this tab, in about a second"],
  ["what",  "what this is, in sixty seconds"],
  ["why",   "why a command line and not, you know, a real interface"],
  ["open",  "the actual instrument"],
  ["help",  "everything else"]
];

/* The whole surface, grouped by what you want to do. Every row runs on tap. */
C.groups = [
  {h: "LISTEN", items: [
    ["tour",      "the guided walk. two minutes; one of them is a banger"],
    ["demo",      "a beat in this tab, right now"],
    ["gallery",   "what people made - every track plays right here"],
    ["charts",    "most forked, most-shared patterns, the tempo spread"],
    ["playlists", "bundles people shared, start to finish"]]},
  {h: "UNDERSTAND", items: [
    ["what",      "what this is, in sixty seconds"],
    ["spec",      "why a song here is source code, and what that buys"],
    ["why",       "why a command line and not, you know, a real interface"],
    ["theory",    "what the machine knows about music"],
    ["language",  "the research article. 21,000 words on why this works"]]},
  {h: "MAKE", items: [
    ["open",      "oontz.sh - the actual instrument, whole, in a tab"],
    ["help",      "every command, including the sharp ones"],
      ["repo",     "the source. all of it, including the synth"],
      ["terms",    "the deal, and `privacy`, in plain english"]]}
];
C.first_visit = "type `tour` and the site walks you through itself.";
C.tour_off = "wandering off - the tour will be here.";
C.tour_1 = [
  {t: "The tour. Step one: it makes noise.", cls: "b"},
  {s: "This is not a video of the product. It is the product."}
];
C.tour_2 = [
  {t: "Step two: the whole idea in one character.", cls: "b"},
  {s: "That kick pattern is text. Change one character, the song changes:"}
];
C.tour_3 = [
  {t: "Step three: everything anyone publishes is source.", cls: "b"},
  {s: "Tap any row and the actual track plays here - the recipe, not a recording."}
];
C.tour_4 = [
  {t: "Step four: because songs are source, music has charts.", cls: "b"},
  {s: "Which pattern is most shared. Which track got forked most. Tap and hear."}
];
C.tour_done = [
  {},
  {t: "That is the story. The rest is you.", cls: "b"},
  {s: "The full instrument is one tab away - free, no account, phone included:"},
  {c: "open", d: "oontz.sh - pads, decks, an AI bandmate, rooms for two"},
  {}
];

C.help = [
  ["demo",                  "start the loop"],
  ["stop",                  "end it"],
  ["kick x...x...x...x...", "change a pattern. x is a hit, . is a rest. try it"],
  ["hat ..x.x.x...x.x.x.",  "hats between the kicks. this is the whole trick"],
  ["bpm 150",               "faster. 60 to 220, no judgement"],
  ["what",                  "the sixty-second version"],
  ["why",                   "the argument"],
  ["theory",               "what the machine knows about music"],
  ["free",                  "the catch. spoiler: there isn't one"],
  ["gallery",               "what other people made"],
  ["play w7k2…",            "hear one, right here. it's the source, not a recording"],
  ["gallery top",           "most played · also: gallery bpm 140-150 · gallery key 8a"],
  ["playlists",             "what people bundled together, playable start to finish"],
  ["spec",                  "why a song here is source code, and what that buys you"],
  ["language",              "the whole reasoning, at length: history, theory, architecture"],
  ["gallery pat x...x...x...x...", "search the actual music: every track playing that pattern"],
  ["gallery like <id>",     "more like this one, scored on structure, reasons included"],
  ["tree <id>",             "the remix family tree: who flipped what"],
  ["charts",                "what the source graph knows: most forked, most-shared patterns, tempos"],
  ["(at oontz.sh) room new", "two browsers, one track, live — the AI is in the room too"],
  ["tour",                  "the guided two-minute walk through everything"],
  ["watch",                 "nothing but the visuals while a track plays. Esc returns"],
  ["open",                  "go to oontz.sh, where the real one lives"],
  ["clear",                 "tidy up"]
];

/* -- what ---------------------------------------------------------------- */
C.what = [
  {t: "oontz is a musical instrument that lives in a terminal.", cls: "b"},
  {},
  {s: "You type a pattern. It becomes a drum machine. 🥁"},
  {},
  {c: "kick x...x...x...x...", d: "four on the floor"},
  {c: "hat  ..x...x...x...x.", d: "hats in the gaps — this is why it feels fast"},
  {c: "bass a1 . a1~ c2",      d: "~ slides between notes, like a 303 does"},
  {},
  {s: "That is the entire interface. There is no mouse. There are no rectangles"},
  {s: "to drag. There is nothing to buy, install, or agree to."},
  {},
  {s: "Under it: a real synthesizer. Every kick is a sine wave with a pitch"},
  {s: "envelope dropping 150Hz to 50Hz in 40 milliseconds, saturated until it"},
  {s: "clips politely. Every hat is white noise through a highpass at 8kHz."},
  {s: "Nothing was recorded. It is all arithmetic, computed while you listen."}
];

/* -- why ----------------------------------------------------------------- */
C.why = [
  {t: "Music software asks you to draw.", cls: "b"},
  {},
  {s: "You open a DAW and you are handed a canvas, a grid, and four hundred"},
  {s: "small rectangles to arrange with a mouse. It is a drawing program that"},
  {s: "happens to make noise. 🖱️"},
  {},
  {s: "Nothing about it can be searched, diffed, copied into a message, or"},
  {s: "explained to another person in one line. Your song is a 400MB binary"},
  {s: "blob that only opens in the program that made it, on the version of that"},
  {s: "program you had at the time. Good luck in five years."},
  {},
  {t: "A pattern is a sentence.", cls: "a"},
  {},
  {s: "kick x...x...x...x..x  —  you just read that. You know what it does. You"},
  {s: "could type it into a text message. You could put it in a git commit."},
  {},
  {t: "And here is the part that actually matters:", cls: "b"},
  {},
  {s: "A three-minute oontz track is 15 kilobytes. Not the compressed audio —"},
  {s: "the SONG. Every pattern, every note, every filter sweep, the whole"},
  {s: "arrangement. Fifteen kilobytes. 📄"},
  {},
  {s: "The same track as audio is about 30 megabytes. So the text version is"},
  {s: "roughly two thousand times smaller.", cls: "ok"},
  {},
  {s: "Which means when you share a track, you are not sending someone a"},
  {s: "recording. You are sending them the source. They can hear it, open it,"},
  {s: "see exactly how the drop was built, change one number, and hear that."},
  {},
  {t: "You share the recipe, not the cake. 🍰", cls: "a2"},
  {},
  {s: "No other music tool works this way, and it is not because nobody thought"},
  {s: "of it. It is because a DAW's output cannot be text. Ours can only be text."}
];

/* -- theory -------------------------------------------------------------- */
C.theory = [
  {t: "The machine is not guessing. 🧠", cls: "b"},
  {},
  {s: "There is a music theory engine underneath, and it is opinionated:"},
  {},
  {c: "the drop belongs 20-40% in", d: "earlier and there's no tension to release"},
  {c: "sections in multiples of 8", d: "dancers and DJs both count in eights"},
  {c: "16-32 bars of plain intro",  d: "or a DJ literally cannot mix into it"},
  {c: "kick owns 40-90Hz alone",    d: "two things in one band is how mixes die"},
  {c: "a drop needs a break first", d: "loud is relative. no contrast, no impact"},
  {},
  {s: "It grades what you make against all of it and hands back a number and a"},
  {s: "list of what is wrong. A well-built track scores in the nineties. A pile"},
  {s: "of loops with a 12-bar section scores zero and gets told why. ✗"},
  {},
  {s: "This is the difference between a generator you have to trust and one you"},
  {s: "can argue with."}
];

/* -- free ---------------------------------------------------------------- */
C.free = [
  {t: "It is free. Genuinely, structurally free.", cls: "b"},
  {},
  {s: "Not free-tier free. Not free-until-we-raise-a-round free. 💸"},
  {},
  {s: "The audio is computed in your browser, on your machine, using your CPU."},
  {s: "There is no render farm. There is no per-minute transcoding bill. When"},
  {s: "you make a five-minute banger at three in the morning, it costs me"},
  {s: "exactly nothing, because I am not involved."},
  {},
  {s: "And storage is 15KB per track. A thousand songs is fifteen megabytes."},
  {s: "That is one photo. 📷"},
  {},
  {s: "An account is an email address, and it buys you exactly two things:"},
  {s: "your songs saved, and the option to publish them. You never need one to"},
  {s: "play. Close this tab and open it tomorrow — still free, still works."}
];

/* -- gallery ------------------------------------------------------------- */
C.gallery_empty = [
  {s: "Nobody has published anything yet. You could be first, which is either"},
  {s: "an honour or a warning depending on your disposition. 🏆"}
];
C.spec = [
  {t: "Source code for music.", cls: "b"},
  {},
  {s: "An MP3 tells you what happened. An oontz file tells you how."},
  {},
  {c: "kick x...x...x...x...", d: "press play. four on the floor"},
  {c: "kick x...x...x...x..x", d: "one character changed. the song changed"},
  {},
  {s: "A complete track - arrangement, notes, automation, even its colors -"},
  {s: "is a few KB of text that renders the same audio every time. So music"},
  {s: "here is diffable, forkable with automatic credit, searchable by its"},
  {s: "actual structure, and readable by the AI that jams alongside you."},
  {},
  {s: "The recording is just a compiled artifact, like a PDF from a document."},
  {s: "The format is documented: github.com/charley-forey/oontz - docs/OONTZ-FORMAT.md"}
];
/* The article is a page, not a terminal command - so this is the trailer for it,
   and the link does the rest. Long-form belongs somewhere you can scroll. */
C.language = [
  {t: "The Song Is the Source", cls: "b"},
  {s: "Notes toward an audio programming language. ~21,000 words."},
  {},
  {s: "Everything behind this: six thousand years of notation, sixty-five years"},
  {s: "of computer music and what each system got right, the nine laws, the"},
  {s: "semantics, why a seeded PRNG breaks a song, the architecture with its"},
  {s: "numbers, the metaphors, the economics - and a conformance checklist you"},
  {s: "can build a rival implementation from."},
  {},
  {s: "Written to be studied, forked and superseded."}
];
C.play_note = "that was the recipe, not a recording — a few KB of text, rendered here. take it apart:";
C.gallery_hint = "each id plays right here: play <the id>. every track is its own source code.";
C.playlists_empty = [
  {s: "No public playlists yet."},
  {s: "Someone signs in at oontz.sh, bundles what they like, types `playlist public` —"},
  {s: "and it shows up here, playable start to finish."}
];
C.playlists_head = [
  {t: "Playlists people shared.", cls: "b"},
  {}
];
C.gallery_head = [
  {t: "Published tracks. Each one is a few KB of text.", cls: "b"},
  {s: "Open any of them and you get the arrangement, not just the audio."}
];

/* -- open ---------------------------------------------------------------- */
C.open = [
  {t: "oontz.sh — the real one.", cls: "b"},
  {},
  {s: "This page is a toy: four tracks, one loop, enough to make the point."},
  {},
  {s: "Over there you get whole songs with intros, builds, drops and breaks;"},
  {s: "two DJ decks with beat-exact sync; a copilot that reads your arrangement"},
  {s: "and tells you what is wrong with it; and a record button. 🎛️"}
];

/* -- errors: even these should teach ------------------------------------- */
C.err_pattern = "a pattern is x for a hit and . for a rest. try: kick x...x...x...x...";
C.err_cmd = function (v) { return v + ": not a command. type help — it is short."; };
C.err_bpm = "bpm takes 60 to 220. techno mostly lives at 130-150.";

C.egg_oontz_done = [
  {s: "that is the whole genre, yes. `demo` has hats in it, if you're fancy."}
];
C.egg_sudo = "this incident will be reported to the groove authorities.";
C.egg_konami = "you found the rave. it wears off in ten seconds, like most raves.";
C.egg_spin = "spinback. obviously.";

g.OONTZ_COPY = C;
})(window);
