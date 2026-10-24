/* Local, deterministic checks. These are observations about extracted text, not an ATS score. */
(function(root){
function inspect(text){
 const clean=text.trim(), words=clean.split(/\s+/).filter(Boolean).length;
 const readable=(clean.match(/[a-zA-ZÀ-ž]/g)||[]).length/Math.max(clean.length,1)>.45;
 const email=/[\w.+-]+@[\w.-]+\.[a-z]{2,}/i.test(clean);
 const contact=email||/(?:linkedin\.com\/in\/|https?:\/\/[^\s]+)/i.test(clean);
 const experience=/\b(experience|employment|work history|professional background)\b/i.test(clean);
 const education=/\b(education|qualifications|certifications?|training|apprenticeship)\b/i.test(clean);
 const skillSection=/\b(skills|expertise|competencies|technical proficiencies)\b/i.test(clean);
 const dates=/\b(?:19|20)\d{2}\s*(?:[-–—]|to)\s*(?:(?:19|20)\d{2}|present|current)/i.test(clean)||/\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(?:19|20)\d{2}/i.test(clean);
 // Require a number attached to a measure or outcome. Dates and phone numbers do not count.
 const measured=/\b\d+(?:[.,]\d+)?\s*(?:%|percent\b|clients?\b|customers?\b|users?\b|projects?\b|people\b|team members?\b|hours?\b|days?\b|weeks?\b)|[$£€]\s*\d/i.test(clean);
 const vague=clean.match(/\b(?:responsible for|helped with|worked on|assisted with|managed social media)\b[^.\n]{0,110}/i);
 const findings=[];
 if(!readable)findings.push({title:'Check the extracted text.',body:'Some text looks difficult to read. Paste a plain-text version so the review and matching have a cleaner starting point.'});
 if(!contact)findings.push({title:'Make it easy to reach you.',body:'No email address or profile link was detected. Add a professional contact method near your name.'});
 if(!experience||!education||!skillSection){const missing=[!experience&&'Experience',!education&&'Education or training',!skillSection&&'Skills'].filter(Boolean);findings.push({title:'Make sections easy to find.',body:'We couldn’t identify '+missing.join(', ')+'. If relevant to your background, use a clear heading. Different wording can also cause this check to miss a section.'})}
 if(experience&&!dates)findings.push({title:'Clarify your timeline.',body:'No familiar employment date pattern was found. Give each role a month and year, for example “June 2022 – Present”. This does not assess gaps.'});
 if(vague)findings.push({title:'Give one responsibility more detail.',quote:vague[0].trim(),body:'Name the task, who it helped and what changed. Add a result only if you can support it; qualitative outcomes are useful too.'});
 else if(experience&&!measured)findings.push({title:'Make your impact more concrete.',body:'No obvious measured example was found. Add scope or an outcome to one role: who you supported, what you delivered, or an improvement you can substantiate. Numbers are optional.'});
 if(words<120)findings.push({title:'Add a little more context.',body:'This is a short extract. For a full CV, include your recent work or projects and the skills you used. If this is only a summary, this finding may not apply.'});
 if(words>1100)findings.push({title:'Try a tighter first read.',body:'The extract is over 1,100 words. Consider trimming repeated details and prioritising work relevant to your target role. Some careers need a longer CV.'});
 const structure=experience&&(education||skillSection);
 const verdict=!readable?'Check the extracted text.':words<120?'A little more context would help.':findings.length?'A few things to review.':'The basics are easy to find.';
 return {words,verdict,checks:[{label:'Text extraction',value:readable?'Readable text':'Review text'},{label:'Section headings',value:structure?'Detected':'Review headings'},{label:'Measured example',value:measured?'Detected':'Not detected'}],findings:findings.slice(0,3)};
}
root.CVReview={inspect};
})(globalThis);
