/* The terms and the privacy notice, in one file both sites load.
 *
 * It lives here and is copied to web/landing/engine/ like the engine is, so
 * `node web/landing/check.js` fails the moment the two drift. A privacy notice that
 * says different things on two domains is worse than not having one.
 *
 * Everything below is written FROM THE CODE, not from a template. If you change what
 * the software collects, this file is part of that change:
 *   - api/main.py users(email)            -> "what we keep"
 *   - api/main.py events(ip, ua, props)   -> "what the server logs", incl. ai_prompt
 *   - web/app/track.js                    -> everything else section 4 lists
 *   - api/main.py EVENT_DAYS = 180        -> the retention number
 *   - the gtag tags in both index.html    -> Google Analytics
 *   - localStorage keys across web/       -> "what stays in your browser"
 */
(function (g) {
  var UPDATED = "25 August 2026";
  var CONTACT = "hello@oontz.sh";

  var L = {};
  L.updated = UPDATED;
  L.contact = CONTACT;

  L.terms = [
    { t: "Terms — oontz.sh and oontz.music", cls: "b" },
    { s: "Last updated " + UPDATED + ". Questions: " + CONTACT },
    {},
    { t: "The short version", cls: "a" },
    { s: "It is free. Your music is yours. Anything you publish is public and other" },
    { s: "people can take it apart, because that is the entire point. Do not use it" },
    { s: "to hurt anyone, and do not expect a refund on nothing." },
    {},
    { t: "1. Using it", cls: "a" },
    { s: "You can use oontz for anything, including commercial work, with no fee and" },
    { s: "no account. You need to be old enough to agree to this where you live." },
    {},
    { t: "2. What you make is yours", cls: "a" },
    { s: "You keep every right you have in the music you make. Publishing does not" },
    { s: "transfer ownership." },
    {},
    { s: "By publishing a track, a playlist or a take, you give us permission to store" },
    { s: "it, show it, and include it in the public gallery, the charts and share" },
    { s: "pages — and you accept that anyone can play it, read its source, and remix" },
    { s: "it. That is not a side effect. A song here is text, and the whole idea is" },
    { s: "that other people can open it and change it. If you do not want that for a" },
    { s: "particular track, do not publish that track." },
    {},
    { s: "Remixes credit the original automatically. Do not strip that." },
    {},
    { t: "3. What you must not publish", cls: "a" },
    { s: "Nothing illegal. Nothing that infringes somebody else's rights. Nothing" },
    { s: "designed to harass, defame or endanger a person. No malware, and nothing" },
    { s: "aimed at breaking the service for everybody else." },
    {},
    { s: "Titles are public. Do not put personal information in them." },
    {},
    { t: "4. We can remove things", cls: "a" },
    { s: "Publishing needs no account here, which is deliberate and which means a" },
    { s: "small amount of what arrives will be rubbish. We can remove any content and" },
    { s: "block any use of the service, without notice, and we do not have to explain" },
    { s: "ourselves. Tell us at " + CONTACT + " if something should not be here." },
    {},
    { t: "5. No warranty", cls: "a" },
    { s: "This is provided as-is. It might break, lose your work, or stop existing." },
    { s: "Nothing here is guaranteed to be available, correct, or permanent, and to" },
    { s: "the extent the law allows we are not liable for what happens if it is not." },
    {},
    { s: "Keep your own copies of anything you care about: `source save` writes the" },
    { s: "whole song to a file, and `export` writes the audio." },
    {},
    { t: "6. The code", cls: "a" },
    { s: "The source is public at github.com/charley-forey/oontz and is covered by" },
    { s: "whatever licence that repository states. These terms are about the hosted" },
    { s: "service, not about the code." },
    {},
    { t: "7. Changes", cls: "a" },
    { s: "If these change, the date at the top changes. Carrying on using the service" },
    { s: "after that is how you accept it." },
    {},
    { s: "Read the other half: `privacy`" }
  ];

  L.privacy = [
    { t: "Privacy — oontz.sh and oontz.music", cls: "b" },
    { s: "Last updated " + UPDATED + ". Questions or deletions: " + CONTACT },
    {},
    { t: "The short version", cls: "a" },
    { s: "You can use the whole instrument without giving us anything. No account is" },
    { s: "needed to make music, to share a link, or to listen. We never store audio." },
    { s: "We do log what you ask the AI, and we do use Google Analytics. Details below," },
    { s: "and they are the honest ones." },
    {},
    { t: "1. If you never sign in", cls: "a" },
    { s: "We hold no account for you. The music you make stays in your browser until" },
    { s: "you choose to publish or share it." },
    {},
    { t: "2. If you sign in", cls: "a" },
    { s: "We store your email address, and a handle if you set one. The email is used" },
    { s: "to send sign-in links and nothing else — no marketing, no list, ever. There" },
    { s: "is no password, because we never wanted to hold one." },
    {},
    { t: "3. What you publish", cls: "a" },
    { s: "Published songs, playlists and takes are stored and shown publicly, with the" },
    { s: "handle you chose or \"anon\". A play counter is kept per track. Takes are" },
    { s: "stored as the command log — a few KB of text — never as audio." },
    {},
    { t: "4. What the server logs", cls: "a" },
    { s: "We record what you do here, not only that you were here. Every record" },
    { s: "carries the time, the page, the referrer, your IP address, your browser's" },
    { s: "user-agent string, a session id, a device id, and your account id if you" },
    { s: "are signed in. What gets recorded, plainly:" },
    {},
    { s: "  every line you type into the terminal, on either site — the whole line," },
    { s: "  as you typed it, not just the ones you send to the AI" },
    { s: "  what you click and what you follow: buttons, links, the text on them" },
    { s: "  where your pointer is, sampled a few times a second and rounded to one" },
    { s: "  of 96 boxes on the screen — coarse activity, not your exact cursor path" },
    { s: "  how far down a page you scroll" },
    { s: "  when a session starts and ends, and how long you stay" },
    {},
    { s: "Prompts you send to the AI are logged on our server too, so they survive" },
    { s: "even when the browser half is blocked. Do not type anything into `ask`," },
    { s: "`jam`, `produce`, `dream` — or into the terminal at all — that you would" },
    { s: "not want us to be able to read." },
    {},
    { s: "This is on unless you turn it off. Section 8 says how." },
    {},
    { s: "These records are deleted after 180 days." },
    {},
    { s: "IP addresses are also held in memory, for under a minute, to rate-limit" },
    { s: "abuse. That is not written to disk." },
    {},
    { t: "5. Who else sees it", cls: "a" },
    { s: "  Railway            hosting; sees traffic to all three services" },
    { s: "  Resend             sends the sign-in emails; sees your address" },
    { s: "  Google Analytics   page views on both sites; sets its own cookies" },
    { s: "  Anthropic          receives your prompt when you use the AI" },
    {},
    { s: "We do not sell anything to anyone, because there is no one to sell it to and" },
    { s: "we would rather not." },
    {},
    { t: "6. What stays in your browser", cls: "a" },
    { s: "Your saved songs, your themes, your command history, your settings, your" },
    { s: "sign-in token — all of it is localStorage on your own machine, not on our" },
    { s: "server. Clearing your browser data removes it and we cannot get it back." },
    {},
    { s: "If you link your own Anthropic key with `key`, it is kept in your browser" },
    { s: "and sent with each request you make. We never write it down." },
    {},
    { t: "7. What we never store", cls: "a" },
    { s: "Audio. Passwords. Payment details. Your Anthropic key. Nothing renders on" },
    { s: "our servers, so the sound you make never leaves your machine unless you" },
    { s: "export it yourself." },
    {},
    { t: "8. Your rights", cls: "a" },
    { s: "Ask us at " + CONTACT + " for a copy of what we hold about you, for it to be" },
    { s: "corrected, or for all of it to be deleted, and we will do it. You can delete" },
    { s: "your own songs at any time from the instrument." },
    {},
    { s: "Type `notrack` on either site to switch off everything in section 4. It" },
    { s: "sets a flag in your browser; type it again to switch it back on. If your" },
    { s: "browser sends Do Not Track we honour that and never start in the first" },
    { s: "place." },
    {},
    { s: "Read the other half: `terms`" }
  ];

  g.OONTZ_LEGAL = L;
})(typeof window !== "undefined" ? window : globalThis);
