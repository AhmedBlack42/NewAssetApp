Corrupted Academy Girl Mod Guide
Contents
Intro	
Folder Structure	
Girl_config.json	
Body_images	
Fullbody	
Vids	
Photo and Video Shoots	
Advanced: Clothing	
Advanced: Events	
Testing	
Tags:	
Girl_config traits:	
Vid Tags	
Shoots	
Tips:	
Config:	
Vids:	
Body Images:	
Fullbody:	
Shoots:	
Clothing:	
Events:	
Other:	
Intro
This is a guide on how to make girl mods for the game Corrupted Academy. This mod is assuming that you have the mod tools available for the game, as it drastically makes the work easier. 
I advise finding a way to get videos of your chosen girl, or at least a good base for short clips. I use private torrents so I can’t help you find stuff there, but shorter videos on big tube sites are typically alright. You’ll also need high quality pictures of the girl, especially full body images. I use vipergirls to find mine, typically it works well.
For converting mp4’s to webm’s, I use handbrake. I use losslesscut for cutting up videos into sufficient content. I use Visual Studio for editing the json files. Don’t use the webm cutter upper tool in the mod tools, it sucks to use (sorry HeX).
To remove backgrounds from pictures, I typically use https://fyrean.itch.io/bgbye-background-remover but sometimes it is overloaded or too busy or something. In those cases I use https://lonetools.com/remove-background . You can also use Gimp if you know how to, or Photoshop if you own it. Those require more effort. I like to get a lot of pictures in case some don’t work rather than try to force one to work.
The guide will be divided into sections, with the most important stuff first, followed by the least. I recommend trying to get some content for everything except events and clothing images.








Folder Structure
If you haven’t yet, I recommend opening up the example girl mod in the folder game/_mods/example_mods/girls/Kiara Cole. She will work as a good template for how to make a girl pack.
All modded girls should go in game/_mods/girls. She’ll have a main folder that should be her name (In our example, Kiara Cole.) Inside that folder should be the girl_config.json and all the folders for her content. The girl_config.json is necessary for her to function.
With the new mod manager, you’ll want to zip just your girl folder. When downloaded through the mod manager, the game will know where to put it.























Girl_config.json
The girl_config.json contains the info that the game will see and use to initialize your girl. Let’s look at Kiara Cole’s config (I am using Visual Studio code, which I recommend for this stuff)

 

The girl’s id is what the game will use for itself as the identifier for the girl. I believe every girl so far has just her name as this, all in undercase and with an underscore as the space. I strongly recommend doing that as it makes everything easier. Keep it in mind for when we get to shared shoots.
Her first name and last name should hopefully not need explanation on what they should be.
Area sensitivity is the modifier that adjusts the sensitivity of the matching area. It is not necessary for the girl to function. If left empty, the game will randomly generate it. 1 means no difference, while 2 is a 100% increase. For Kiara, these stats mean her breasts are slightly more sensitive. 
Traits are where you assign her traits. They can be custom traits, like Kiara’s sensitive nipples trait, or default like her hair, eye, and boob size. You should have her hair color, eye color, and boob size here at the minimum, and should also include her race if she isn’t white. There is a list of traits at the end of this guide.
If you want to make a custom trait like the one here, you can do so. They are out of the scope of this beginner guide.
Generate_additional_traits determines if the game will make new traits for her upon generating her. If it is True, she will get random default traits upon generation. If false, she’ll only have what you give her. I recommend doing True if you don’t fill her up with traits, as without a good amount of traits she’ll look barren.
Lastly, include whatever your username is for modder. It’s not necessary but helpful for determining who has who.
For mothers: moms work a bit different than the girls. Shay Sights is the example mom in the \game\_mods\example_mods\mothers folder. She uses a mother_config.json, and can have a daughter_id that ties her to the daughter. If you have a daughter to use with her, put it here. If you don’t have one, she’ll be used for any girl, or can be chosen for a girl in game. 










Body_images
UPDATE: Next update (as of Jan 4th 2026) will involve more accurate tagging for body images. As such, prior tags may be incorrect.
The tags will now obey the tag system that videos have, with it being {main_tag},{main_tag2}-{sub_tag},{sub_tag2}.webp. This means that something like a face pic with cum on it would be face-cum.webp. Main tag is face, subtag is cum. Corruption tags (conservative, whore for example) work for subtags, as well as cum or creampie (or both if you wish) and locations.
The number for an image matters as well. Let’s say we have ass1, boobs1, pussy1 and face1. The game will try to use them together if possible. 
The first, most important folder is body_images. Inside are the images that the game uses for the girl. Assume all pictures in the game should be .webp. Open Kiara’s now.

Here are her photos. Here’s the recommended sizes for the images:
Girl Image Dimensions: 
portrait/tportrait(1:1): 350x350
face(1:1): 500x500
boobs(2.06:1): 495x240
pussy(1.04:1): 245x235
ass(2.06:1): 495x240
legs(1.04:1): 245x235
If they’re smaller than this, the game will stretch them up to fit, which looks bad. If they’re the wrong aspect ratio the game will stretch or smoosh it to fit, which looks worse. I use gimp to make a shape the size of what I need and snip it from the picture. You can make them bigger if you wish but it’s a bit of a waste of space. 
Portrait and tportrait should have a transparent background. Tportrait is used when she’s topless, so make sure she is. These are the little face icons that show up during dialogue. Face is used in stuff like menus and sex interaction, and looks better with a background in my opinion, but it doesn’t matter too much if it’s transparent.
Fullbody
I’d argue that fullbody pics are more important than actual videos with patch 0.4, but that’s my opinion. These will be the pictures that show when out and about on the map, and other places like in her bedroom. It looks really ugly if not done right, so I think it’s really important. Open Kiara’s now.

Ignore the original folder for now. Notice the names of the images: bare, bikini, clothed, topless, underwear. These are the most important pics to get.
The pictures should be at least 1500p high. This might be difficult to do, even Kiara’s aren’t all right. They’re all transparent backgrounds, and trimmed down to the minimum on each side as the game will resize the picture.
If you open the original folder you’ll see the photos HeX used to get these, if you want an idea of what to look for. 
The possible fullbody types are currently:
shower 
maid 
nurse
work 
uniform 
athletic 
swimsuit
bikini 
bare 
clothed

Fullbodys check the clothing state of a girl. This means you can have a photo that is clothed on top but she is bottomless below. Say our girl is wearing a shirt but no pants or panties. We’d call that {clothed-bottomless.webp}. If we wanted it to only be used when she’s still shy, we could make it {clothed-bottomless,conservative.webp} for example. The underwear tag can be used this way as well I think. 


Vids
This is likely the biggest part of the process. Here are all the unique videos that play during actions in game. 
For this I’ll be describing the mod tool video helper, as it makes the process much easier.


Intro
This is a guide on how to make girl mods for the game Corrupted Academy. This mod is assuming that you have the mod tools available for the game, as it drastically makes the work easier. 
I advise finding a way to get videos of your chosen girl, or at least a good base for short clips. I use private torrents so I can’t help you find stuff there, but shorter videos on big tube sites are typically alright. You’ll also need high quality pictures of the girl, especially full body images. I use vipergirls to find mine, typically it works well.
For converting mp4’s to webm’s, I use handbrake. I use losslesscut for cutting up videos into sufficient content. I use Visual Studio for editing the json files. Don’t use the webm cutter upper tool in the mod tools, it sucks to use (sorry HeX).
To remove backgrounds from pictures, I typically use https://fyrean.itch.io/bgbye-background-remover but sometimes it is overloaded or too busy or something. In those cases I use https://lonetools.com/remove-background . You can also use Gimp if you know how to, or Photoshop if you own it. Those require more effort. I like to get a lot of pictures in case some don’t work rather than try to force one to work.
The guide will be divided into sections, with the most important stuff first, followed by the least. I recommend trying to get some content for everything except events and clothing images.








Folder Structure
If you haven’t yet, I recommend opening up the example girl mod in the folder game/_mods/example_mods/girls/Kiara Cole. She will work as a good template for how to make a girl pack.
All modded girls should go in game/_mods/girls. She’ll have a main folder that should be her name (In our example, Kiara Cole.) Inside that folder should be the girl_config.json and all the folders for her content. The girl_config.json is necessary for her to function.
With the new mod manager, you’ll want to zip just your girl folder. When downloaded through the mod manager, the game will know where to put it.























Girl_config.json
The girl_config.json contains the info that the game will see and use to initialize your girl. Let’s look at Kiara Cole’s config (I am using Visual Studio code, which I recommend for this stuff)

 

The girl’s id is what the game will use for itself as the identifier for the girl. I believe every girl so far has just her name as this, all in undercase and with an underscore as the space. I strongly recommend doing that as it makes everything easier. Keep it in mind for when we get to shared shoots.
Her first name and last name should hopefully not need explanation on what they should be.
Area sensitivity is the modifier that adjusts the sensitivity of the matching area. It is not necessary for the girl to function. If left empty, the game will randomly generate it. 1 means no difference, while 2 is a 100% increase. For Kiara, these stats mean her breasts are slightly more sensitive. 
Traits are where you assign her traits. They can be custom traits, like Kiara’s sensitive nipples trait, or default like her hair, eye, and boob size. You should have her hair color, eye color, and boob size here at the minimum, and should also include her race if she isn’t white. There is a list of traits at the end of this guide.
If you want to make a custom trait like the one here, you can do so. They are out of the scope of this beginner guide.
Generate_additional_traits determines if the game will make new traits for her upon generating her. If it is True, she will get random default traits upon generation. If false, she’ll only have what you give her. I recommend doing True if you don’t fill her up with traits, as without a good amount of traits she’ll look barren.
Lastly, include whatever your username is for modder. It’s not necessary but helpful for determining who has who.
For mothers: moms work a bit different than the girls. Shay Sights is the example mom in the \game\_mods\example_mods\mothers folder. She uses a mother_config.json, and can have a daughter_id that ties her to the daughter. If you have a daughter to use with her, put it here. If you don’t have one, she’ll be used for any girl, or can be chosen for a girl in game. 










Body_images
UPDATE: Next update (as of Jan 4th 2026) will involve more accurate tagging for body images. As such, prior tags may be incorrect.
The tags will now obey the tag system that videos have, with it being {main_tag},{main_tag2}-{sub_tag},{sub_tag2}.webp. This means that something like a face pic with cum on it would be face-cum.webp. Main tag is face, subtag is cum. Corruption tags (conservative, whore for example) work for subtags, as well as cum or creampie (or both if you wish) and locations.
The number for an image matters as well. Let’s say we have ass1, boobs1, pussy1 and face1. The game will try to use them together if possible. 
The first, most important folder is body_images. Inside are the images that the game uses for the girl. Assume all pictures in the game should be .webp. Open Kiara’s now.

Here are her photos. Here’s the recommended sizes for the images:
Girl Image Dimensions: 
portrait/tportrait(1:1): 350x350
face(1:1): 500x500
boobs(2.06:1): 495x240
pussy(1.04:1): 245x235
ass(2.06:1): 495x240
legs(1.04:1): 245x235
If they’re smaller than this, the game will stretch them up to fit, which looks bad. If they’re the wrong aspect ratio the game will stretch or smoosh it to fit, which looks worse. I use gimp to make a shape the size of what I need and snip it from the picture. You can make them bigger if you wish but it’s a bit of a waste of space. 
Portrait and tportrait should have a transparent background. Tportrait is used when she’s topless, so make sure she is. These are the little face icons that show up during dialogue. Face is used in stuff like menus and sex interaction, and looks better with a background in my opinion, but it doesn’t matter too much if it’s transparent.
Fullbody
I’d argue that fullbody pics are more important than actual videos with patch 0.4, but that’s my opinion. These will be the pictures that show when out and about on the map, and other places like in her bedroom. It looks really ugly if not done right, so I think it’s really important. Open Kiara’s now.

Ignore the original folder for now. Notice the names of the images: bare, bikini, clothed, topless, underwear. These are the most important pics to get.
The pictures should be at least 1500p high. This might be difficult to do, even Kiara’s aren’t all right. They’re all transparent backgrounds, and trimmed down to the minimum on each side as the game will resize the picture.
If you open the original folder you’ll see the photos HeX used to get these, if you want an idea of what to look for. 
The possible fullbody types are currently:
shower 
maid 
nurse
work 
uniform 
athletic 
swimsuit
bikini 
bare 
clothed

Fullbodys check the clothing state of a girl. This means you can have a photo that is clothed on top but she is bottomless below. Say our girl is wearing a shirt but no pants or panties. We’d call that {clothed-bottomless.webp}. If we wanted it to only be used when she’s still shy, we could make it {clothed-bottomless,conservative.webp} for example. The underwear tag can be used this way as well I think. 


Vids
This is likely the biggest part of the process. Here are all the unique videos that play during actions in game. 
For this I’ll be describing the mod tool video helper, as it makes the process much easier.


Intro
This is a guide on how to make girl mods for the game Corrupted Academy. This mod is assuming that you have the mod tools available for the game, as it drastically makes the work easier. 
I advise finding a way to get videos of your chosen girl, or at least a good base for short clips. I use private torrents so I can’t help you find stuff there, but shorter videos on big tube sites are typically alright. You’ll also need high quality pictures of the girl, especially full body images. I use vipergirls to find mine, typically it works well.
For converting mp4’s to webm’s, I use handbrake. I use losslesscut for cutting up videos into sufficient content. I use Visual Studio for editing the json files. Don’t use the webm cutter upper tool in the mod tools, it sucks to use (sorry HeX).
To remove backgrounds from pictures, I typically use https://fyrean.itch.io/bgbye-background-remover but sometimes it is overloaded or too busy or something. In those cases I use https://lonetools.com/remove-background . You can also use Gimp if you know how to, or Photoshop if you own it. Those require more effort. I like to get a lot of pictures in case some don’t work rather than try to force one to work.
The guide will be divided into sections, with the most important stuff first, followed by the least. I recommend trying to get some content for everything except events and clothing images.








Folder Structure
If you haven’t yet, I recommend opening up the example girl mod in the folder game/_mods/example_mods/girls/Kiara Cole. She will work as a good template for how to make a girl pack.
All modded girls should go in game/_mods/girls. She’ll have a main folder that should be her name (In our example, Kiara Cole.) Inside that folder should be the girl_config.json and all the folders for her content. The girl_config.json is necessary for her to function.
With the new mod manager, you’ll want to zip just your girl folder. When downloaded through the mod manager, the game will know where to put it.























Girl_config.json
The girl_config.json contains the info that the game will see and use to initialize your girl. Let’s look at Kiara Cole’s config (I am using Visual Studio code, which I recommend for this stuff)

 

The girl’s id is what the game will use for itself as the identifier for the girl. I believe every girl so far has just her name as this, all in undercase and with an underscore as the space. I strongly recommend doing that as it makes everything easier. Keep it in mind for when we get to shared shoots.
Her first name and last name should hopefully not need explanation on what they should be.
Area sensitivity is the modifier that adjusts the sensitivity of the matching area. It is not necessary for the girl to function. If left empty, the game will randomly generate it. 1 means no difference, while 2 is a 100% increase. For Kiara, these stats mean her breasts are slightly more sensitive. 
Traits are where you assign her traits. They can be custom traits, like Kiara’s sensitive nipples trait, or default like her hair, eye, and boob size. You should have her hair color, eye color, and boob size here at the minimum, and should also include her race if she isn’t white. There is a list of traits at the end of this guide.
If you want to make a custom trait like the one here, you can do so. They are out of the scope of this beginner guide.
Generate_additional_traits determines if the game will make new traits for her upon generating her. If it is True, she will get random default traits upon generation. If false, she’ll only have what you give her. I recommend doing True if you don’t fill her up with traits, as without a good amount of traits she’ll look barren.
Lastly, include whatever your username is for modder. It’s not necessary but helpful for determining who has who.
For mothers: moms work a bit different than the girls. Shay Sights is the example mom in the \game\_mods\example_mods\mothers folder. She uses a mother_config.json, and can have a daughter_id that ties her to the daughter. If you have a daughter to use with her, put it here. If you don’t have one, she’ll be used for any girl, or can be chosen for a girl in game. 










Body_images
UPDATE: Next update (as of Jan 4th 2026) will involve more accurate tagging for body images. As such, prior tags may be incorrect.
The tags will now obey the tag system that videos have, with it being {main_tag},{main_tag2}-{sub_tag},{sub_tag2}.webp. This means that something like a face pic with cum on it would be face-cum.webp. Main tag is face, subtag is cum. Corruption tags (conservative, whore for example) work for subtags, as well as cum or creampie (or both if you wish) and locations.
The number for an image matters as well. Let’s say we have ass1, boobs1, pussy1 and face1. The game will try to use them together if possible. 
The first, most important folder is body_images. Inside are the images that the game uses for the girl. Assume all pictures in the game should be .webp. Open Kiara’s now.

Here are her photos. Here’s the recommended sizes for the images:
Girl Image Dimensions: 
portrait/tportrait(1:1): 350x350
face(1:1): 500x500
boobs(2.06:1): 495x240
pussy(1.04:1): 245x235
ass(2.06:1): 495x240
legs(1.04:1): 245x235
If they’re smaller than this, the game will stretch them up to fit, which looks bad. If they’re the wrong aspect ratio the game will stretch or smoosh it to fit, which looks worse. I use gimp to make a shape the size of what I need and snip it from the picture. You can make them bigger if you wish but it’s a bit of a waste of space. 
Portrait and tportrait should have a transparent background. Tportrait is used when she’s topless, so make sure she is. These are the little face icons that show up during dialogue. Face is used in stuff like menus and sex interaction, and looks better with a background in my opinion, but it doesn’t matter too much if it’s transparent.
Fullbody
I’d argue that fullbody pics are more important than actual videos with patch 0.4, but that’s my opinion. These will be the pictures that show when out and about on the map, and other places like in her bedroom. It looks really ugly if not done right, so I think it’s really important. Open Kiara’s now.

Ignore the original folder for now. Notice the names of the images: bare, bikini, clothed, topless, underwear. These are the most important pics to get.
The pictures should be at least 1500p high. This might be difficult to do, even Kiara’s aren’t all right. They’re all transparent backgrounds, and trimmed down to the minimum on each side as the game will resize the picture.
If you open the original folder you’ll see the photos HeX used to get these, if you want an idea of what to look for. 
The possible fullbody types are currently:
shower 
maid 
nurse
work 
uniform 
athletic 
swimsuit
bikini 
bare 
clothed

Fullbodys check the clothing state of a girl. This means you can have a photo that is clothed on top but she is bottomless below. Say our girl is wearing a shirt but no pants or panties. We’d call that {clothed-bottomless.webp}. If we wanted it to only be used when she’s still shy, we could make it {clothed-bottomless,conservative.webp} for example. The underwear tag can be used this way as well I think. 


Vids
This is likely the biggest part of the process. Here are all the unique videos that play during actions in game. 
For this I’ll be describing the mod tool video helper, as it makes the process much easier.


Tags:
Here are the tags and traits that are built into the game. Note that a lot more may exist in mods, but they won’t be covered here.
Girl_config traits:
These have tiers of rarity when normally generated. If you want you can load up on the really strong ones, but keep in mind balance if you care.
Super Legendary Rarity:
"nympho"
"onanist"
"naturist"
"horny"
"squirter"
Of these, I think nympho and naturist are the strongest.
Legendary Rarity:
"brilliant"
"famous"
"kind"
Brilliant is really good. Anything that buffs intellect gain makes managing the girl easier. Kind seems weak for a legendary trait but it’s not my game to balance.
Epic Rarity:
"noble"
"magnetic"
"honest"
"secretive"
Noble buffs int, so same goodness as brilliant. Honest is our first bad trait, as it makes her more likely to snitch to her mom. Both honest and secretive are considered traits that can only apply to the girl (moms have no one they can report to) so no need to add them to moms.
Rare traits:
"emotional"
"rich"
"photogenic"
Rich is a pretty bad trait. Girls who are modest or broke are more likely to accept any of the offers where you pay them. When confiscating girl’s clothes that aren’t rule breaks, rich girls will never let you pay for the clothes. Rich also seems more common than the other money ones, not sure what’s going on with generation there.
Uncommon traits:
"athletic"
Weirdly only one uncommon trait. Also, sponsors can prefer this one. I’m assuming Fit and Fast like it. Fit and Fast has a very good mod that gives them content in game, so they’re a great sponsor to do, especially because they’re early. Probably should only give this to girls who fit the description, as it is a physical trait (not technically, but it's referring to her body)
Common traits:
"obedient"
"provocative"
"sharp"
These are all good, but just a little good.
Negative traits:
Despite the name, these aren’t all negative for you. Also there’s negative traits that came before this. They do have rarities but HeX forgot to label what’s what.
Legendary negative traits:
"broke"
Despite being legendarily bad, it’s really good for you, the corrupt financial manipulator.
Epic negative traits:
"stressed"
She’ll gain more pressure.
Rare negative traits:
"dumb"
This one is bad, but you can remove it if you get her intelligence over 30. Also, there’s a unique event if you try to cum on a girl’s food and she is dumb and unwilling. 
Uncommon negative traits:
"rebellious"
"cold"
"modest"
Cold is removed when affection goes above 35. Modest is the middle ground between rich and poor. Apparently the wealth traits can change if the girl is rich or poor enough. Modest is good in my opinion.
Physical traits
These are more important for you, the pack maker. You don’t have to add the other traits, but you need to add these. They determine what generic videos can play, so don’t screw these up.
Race traits:
"asian"
"black"
"latina"
The traits don’t have any stat adjustments behind them (thank God.) If there is no trait, the game assumes that the girl is white. Most of the girls are white in this game, at least so far.
Hair traits:
"auburn_hair"
"blonde_hair"
"brown_hair"
"black_hair"
"red_hair"
"colored_hair"
"white_hair"
So blonde with an e, and colored without the u.
Eye color traits:
"blue_eyes"
"brown_eyes"
"hazel_eyes"
"green_eyes"
"grey_eyes"
I don’t really know if the game checks for these to be honest.
Boobs traits:
"small_boobs"
"small_boobs_fake"
"average_boobs"
"average_boobs_fake"
"big_boobs"
"big_boobs_fake"
Notably, big boobs and big boobs fake increase breast sensitivity. This tag is important for determining generic vids to play. I think if she has big fake boobs that just tagging big_boobs_fake will be suffice, but to be safe you can add both. Also, who the hell has small fake boobs?
Big Ass trait:
"big_ass"
Increases ass sensitivity. Use when the ass is phat.
If you want to try adding a modded trait, look at Kiara Cole’s example girl_config for an example, and game/scripts/databases/trait_database_ren.py for these traits in game.
Vid Tags
There’s a few different types of tags for vids. Each vid has one main tag and likely one or more sub tags. The game will give preference to specific girl videos over generic ones (unless you turn off a setting) and will then determine what to play from those based on the sub tags. These are all in the video tag tool, but I’ll add them here for easier reading. I’ll separate them into body parts (head, breasts, pussy, ass, legs) and then other sections that don’t apply there.
Main Tags:
Face:
"kiss"
"rimjob"
"use_mouth"
"facial"
"creampie_mouth"
Do note that rimjob is player GETTING a rimjob from her, not giving her one. That’s an ass action. Use mouth is face fucking or deep throat, and creampie mouth is finishing in her mouth (a lot of modders add facials that are aimed at tongue as this)
Boobs:
"grope_boobs"
"slap_boobs"
"pinch_nipple"
"fuck_boobs"
"cumshot_boobs"
Depending on what you got, I’d put sucking nipple clips as pinch nipple. Cumshot boobs is a cumshot video.
Pussy:
"grope_pussy"
"tease_clit"
"finger_pussy"
"lick_pussy"
"fuck_pussy"
"cumshot_pussy"
"creampie_pussy"
Depending on the scene, grope pussy and tease clit might be interchangeable, but I can never find that thing. Cumshot pussy is cumming on her pussy, while creampie is in it. Creampie can only be done when finishing from fuck_pussy.
Ass:
"grope_ass"
"slap_ass"
"wedgie"
"spank_ass"
"tease_ass"
"finger_ass"
"lick_ass"
"fuck_ass"
"cumshot_ass"
"creampie_ass"
Lick ass is girl GETTING a rimjob, not her doing one. For a lot of girls you can likely do both slap and spank ass for the same action, but spank is supposed to be harsher. Same logic with the cumshot and creampie on ass as the vaginal counterpart.
Legs:
"grope_thighs"
"fuck_thighs"
"cumshot_thighs"
Honestly don’t go crazy trying to get all these. Thigh fucking seems pretty rare, so I add footjobs here, though there is a mod tag for that.
Removing and Stripping tags:
Different clothing parts have videos for removing and stripping them, as well as tearing them. If you’ve played this game you likely know what they are conceptually. Important to remember: REMOVING is PLAYER removing her clothes, STRIPPING is HER removing her clothes. The stripping vids occur when she strips for you at her house or in the bathroom, and when she chooses to strip in an exam.
General remove / strip:
Remove_bra
Remove_lower
remove_panties
remove_shoes
remove_socks
remove_upper
strip_bra
strip_lower
strip_outer
strip_panties
strip_shoes
strip_socks
strip_upper
These general ones should have a video if applicable before you add the specific clothing types. For example, if I only have a video for a girl removing high heels, I’ll use that for strip_shoes rather than strip_heels.
Lower and Upper refer to pants-like clothing and shirt-like clothing. Outer refers to jackets and sweaters. Sock can be anything from socks to lingerie to pantyhose, they’re just on her legs in exam.
There are also tearing vids that can play:
tear_bra
tear_lower
tear_outer
tear_panties
tear_socks
tear_upper
Good luck finding some vid where you the outer jacket or sweater is physically torn.
Specific Clothes tags
Add remove_, strip_, or tear_ to the beginning of these, I’m not writing it all out again. Also, use the vid tagger tool if you’re not.
dress
flats
heels
jeans
leggings
onepiece
pantyhose
shirt
shorts
skirt
sneakers
stockings
Flats are a flat soled shoe, heels are high heels, leggings are stuff like yoga pants, onepiece is a onepiece swimsuit or leotard, sneakers are a type of shoe, stockings a type of long sock.
Other Main Tags
handjob
cum_in_panties
cum_on_panties
masturbate
orgasm
wear_cum_panties
remove_buttplug
insert_buttplug
gloryhole_blowjob
gloryhole_creampie_mouth
gloryhole_fuck_pussy
gloryhole_creampie_pussy
anal_lesson
oral_lesson
vaginal_lesson
girl_aroused_reaction
tease_lower
tease_upper
lotion_rub
flash_ass
cum_on_food
cum_in_coffee
drink_coffee
cum_in_drink
milk_in_coffee
golden_shower
reverse_shower
pee
Masturbate is the girl masturbating, orgasm is her orgasming and plays if there’s not a specific orgasm vid to play (more on that in a bit), wear cum panties is her putting on a pair of panties with cum in it (I just do her putting any pair on), the lesson ones are what play when you visit a girl who is teaching a class if she is a teacher (I put lesbian group scenes in here if I got them), girl aroused reaction is what plays when she sees you masturbating in class, tease lower and upper play when she tries to tempt you to bang her in class (upper is limited to face/boob scenes, while lower is pussy/ass), flash ass plays when you walk with her in park, cum in edible stuff plays when you cum on her stuff at cafeteria or bar, golden shower is YOU peeing on her, reverse is HER peeing on you, pee is just her peeing.
The _orgasm
The female orgasm is no longer a mystery! Well, it’s still hard to understand, but hopefully I can teach you.
The _orgasm tag can be added to a video to denote it as the girl orgasming during that action. If we had a video of a girl squirting while riding a dick, then we could add this tag to denote it as that, making fuck_pussy_orgasm.
Do note that these videos will not play as a normal action. The fuck_pussy_orgasm we made will never play when a fuck_pussy video is called, nor will a fuck_pussy play for fuck_pussy_orgasm.
What this means is that you should have a generic orgasm video that will cover any orgasm the girl has that you don’t have a video for. The girl can orgasm from a lot of things that don’t make sense (it’s porn logic), so you will likely want at least one orgasm to catch the ones that you can’t fill. I’d keep this either really zoomed in on her face, or her masturbating.
Masturbate, fuck pussy, lick pussy, tease clit, grope pussy and fuck ass should be easier ones to find orgasms for, and stuff that will likely lead to an orgasm in game.
Sub Tags
The sub tags come after the main tags. These are how you prevent videos that do not match the in game context from playing. Here’s a list:
Physical Traits
I’m not actually including these as I am assuming this is a guide for girl packs, not generic vids. The game knows your girls traits, and will always prefer her videos over generic ones for this situation. If you’re making a generic video pack, use these, but refer to the video tagging tool.
Clothing tags:
bare
bot
bra
buttplug
clothed
lingerie
nobot
nobra
nopanty
notop
panty
top
Bare is naked, nude, bare naked, birthday suit, you get the picture. Girl lacks any clothes. You will have a lot of these.
Clothed is a girl fully clothed. This means shirt, pants, bra, panties (sock and shoes don’t count)
Bot = bottom (pants, shorts, leggings), top = top (shirt, tank top).
Anything with no in front of it means she lacks this piece. If you have a vid where she is in only panties and bra, it would be notop,nobot,panty,bra. If she’s totally naked, just use bare.
Specific Tags
If you have a bunch of different vids with different clothing, you can use specific tags to further specialize the vids. Just know that you’ll likely not get everything, and that’s ok. Make sure you have enough vids to cover all general options first (if I have a lot of fuck pussy vids, I’ll try to make them more specific, but if I have one wedgie vid, I’ll avoid doing so).
Outer:
hoodie
jacket
These are for stuff she wears over her shirt. A bit rare to find, and it’s really easy to strip this piece of clothing, so don’t sweat this.
Upper:
cheerleader_top (MODDED)
corset
dress
onepiece
shirt
transparent_dress
transparent_upper
Note that cheerleader_top comes from a mod, and a popular one at that. It won’t be played if the mod isn’t installed. Onepiece is a onepiece bathing suit or leotard
Lower
cheerleader_skirt (MODDED)
jeans
leggings
shorts
skirt
Same note about the cheerleader piece.
Panties
transparent_panties
Socks
fishnet
pantyhose
stockings
Corruption Levels
These tags allow the vid to be played when the girl is at a specific corruption value. I like to use conservative if she seems unwilling, while I use whore or ultimate_whore for when she’s really slutty. Generally, I don’t overdo it.
Conservative
Slut
Whore
Ultimate_whore
They range from low to high.
Participants
These tags change the video into threesomes. Use them if she has threesomes.
tp_male
tp_fem
tp stands for third party. Male for 2 dudes, fem for 2 girls. If a video is marked as a threesome with these tags, they will never play for one on one sex, but one on one vids can play during threesomes. Also, only one tag at a time. Jury’s out on scenes with a transgendered character.
Race
Same idea as physical traits. If you tagged it right, girl’s race is already covered. I will note these as if the girl is one of these, you should ensure she’s tagged as such.
"black"
"asian"
"latina"
There are generic vids to account for these. If the girl is white, don’t add anything.
Locations
These add significant weight to where the vid can be played, but if you only have a classroom video of an action, it will play anywhere.
bathroom
bar
beach
cafeteria
class
clinic
coffee_shop
home
locker_room
mall
office
park
pier
shower
lounge
Bathroom is the bathroom at the bar (so think cramped stall stuff). Clinic is the nurse office in the school. Home is both your and the girl’s home. Locker room is the shower area, but not IN the shower. Office is your office. Shower is the locker room, and IN the shower (you can ask to bone her in the shower specifically). Lounge is the teacher’s lounge.
Female_ and Lesbian_
Adding these differentiates the video into a lesbian scene. 
FEMALE should be used when the giver is a generic woman doing the action on your girl. For Kiara, female_lick_pussy means that some girl is eating Kiara’s pussy.
LESBIAN should be used when the giver is your girl. For Kiara, this would be her eating some girl’s pussy.
Do note there’s some weirdness when you select this tag in the app. Anything that adds a prefix must be selected before you select the action. If you click the wrong thing for these tags, you’ll have to clear selections. I don’t really know why and I should tell HeX.
Shoots
The shoot helper tool will help you out with these tags. There’s a main action, clothing state, participants and other tags.












Tips:
Config:
Please include your name, as it makes finding out who did what easier if we have questions or issues with the pack.
Make sure you get the body tags right, especially race if she has it. If she’s black and you forget this, you’ll have a bunch of generic white girl vids play, which sucks. 
These days I don’t really like touching the sensitivity unless you have a girl with a specific niche. Buffing the sensitivity up works nicely to promote using that part more, like Brittney White’s boobs, while you can nerf the body part to shy away from that, like Rae Black and her absence of anal. As sensitivity affects both pressure and arousal gain, having lower value can still be useful, as it won’t pressure her as much.
For traits, I like to keep random on if I’m not doing anything special with custom traits. It keeps stuff unique between runs. Also, intellect buffing traits are really good, as are corruption gaining ones. A girl being broke is better than her being rich as you can financially manipulate her. Keep that in mind if you choose traits.
Vids:
There’s a lot of ways to go about getting these. I’m a perfectionist who downloads as many videos as I can to add as much as I can. You can scour places like Pornhub gifs to find webms already cut that might fit. I recommend you choose videos that are something like 1920x1080 and are at least 720p.
For length, I try to keep it around 10 seconds. It can be shorter or longer, but avoid really long videos. 
For tags that I would say are essential, look for these:
Fuck_pussy, blowjob, lick_pussy, facial,grope_ass, grope_pussy, grope_boobs, tease_clit, finger_pussy, kissing, masturbate, orgasm
Hard to say you’re really a porn star if you haven’t done these things. They’re all pretty common to see in game. Of note, orgasm is the generic orgasm video that will play if the girl doesn’t have a specific orgasm video for an action. I’d advise at least one of these if you can’t find orgasms of other actions, and try to keep it to something like her masturbating as it can trigger off stuff she does alone.
These ones are good to find but not always possible:
Any cumshot or creampie, fuck_ass or anything butthole related, use_face, grope_thighs, slap and spank_ass, pinch_nipples, rimjobs, buttplugs, girl_aroused_reaction, teasing ass and top, flashing ass, modded vids
These ones are somewhat common in gameplay but a girl might never do them. Don’t assume every porn star does anal or eats ass, for example. You can pretend that a sex scene is anal if its doggy style and you can’t actually see penetration, for example. Girl aroused reaction is how she reacts when you openly masturbates in class. Teasing is when she teases you in class which gives you the option to use her. Some mods add stuff like footjobs, slapping face with cock, or sucking nipples. Not everyone will have these mods, so you don’t necessarily need them.
The rest of the actions in the video tag tool I would call very niche. Good luck finding vids for cumming in food, for example. Don’t stress if you can’t get those.
For the lessons, these are the vids that play when you check in on her if she’s teaching a class. I just use any group lesbian scene if she has it. This is really niche so no worries if you can’t find it. 
I value stripping videos highly. Considering the events where she strips down for you, having it mirror her actual state of dress is helpful. Consider possible clothing combos, like removing dress with panties but no bra. There’s a lot of possible combos. If the videos aren’t tagged perfectly, you can have the issue of her stripping her bra while wearing no panties, only to strip her panties off while wearing a bra. This is pretty pedantic however.
Removing clothes is a bit of the same idea as stripping but not as big imo. Do note that it might be difficult to find these. If you want, you can use strip and remove interchangeably.
Corruption level tagging should be used sparingly. I only use it for scenes where she looks actively unhappy (conservative) or she looks super slutty, like spit flying everywhere in a deep throat scenes (whore or ultimate_whore). You’ll have to accept that a lot of vids where she’ll have conservative reactions, she’ll be acting like a porn star. That’s what she is.
Body Images:
Include more than one of each type for some variety. When looking for photoshoots, look for good pics that can fit here. I try to keep any clothing out of these, as they show when she’s totally bare. I find it confusing if it looks like she still has socks or a skirt on despite being bare.
Fullbody: 
These currently only use corruption tags for specifying between each other. Up to you if you can find clothed-conservative vs clothed-whore. At least get the ones that are in the Kiara example, as those ones nearly always show up. The game will default to those if it can’t do the stuff like nurse, for example.
Try to keep them as actual full bodies, with a clear background. They look terrible if she’s not showing her full body in them, or if the background is still in the picture.
Shoots:
Double check these before publishing. I’ve done things like including multiple girls in a solo shoot, used the wrong config title, forget that I have closeup selected, stuff like that. 
When collecting my photos, I grab a set I like off of vipergirls or wherever else and try to get around 20. Evenly choose them through the set you have so as to have some progression while shooting.
Its nice to have some low lewdness stuff for the early game, as girls won’t do the extreme stuff without a rule passing or her being really slutty. 
For videoshoots, I use videos that don’t really fit stuff I could tag. This might not really be possible with some girls. If it has some weird storyline you can try to incorporate that. 
With shared shoots, do note that you need these girls in your active game to actually do it. Thus adding a shoot with something like 5+ specific girls might seem cool, but good luck actually assembling them all at once in gameplay. If you have some massively long save with every girl then I guess you’re good to go.
Clothing:
I don’t really recommend doing this, as the effort is a lot for a minor effect. The nice part about using it on someone like Brittney White is that it keeps her proportions consistent, so her big boobs will stay big in these pics. It’s neat, and if you really like the process of pack making and want to go the extra mile, go ahead. Just note that nearly every pack so far does not do this.
Other:
Should you go for quantity, or quality? Hopefully you can get both, but trying to find everything the girl has done can be really hard. 
When choosing a girl to do, make sure you actually enjoy her as a model. You’ll be watching a lot of her, and if you’re not a fan then it’ll feel like work. I’m not really a fan of Jessica Robbins, so that pack wasn’t very fun. Also, note what she’s done a lot of and what she hasn’t. Some girls do anal, some don’t. 
I go ahead and assume the race of the player is white. Most of the generic videos have a white dude in them, and most of the portraits are a white guy. It’s up to you if you want to include interracial scenes in your vids. Personally, they work well for videoshoots, which otherwise are hard to choose as distinct. If she’s only done a main tag like anal or something in an interracial video, then I’d use it for that instead of a videoshoot, as I think getting those tags are more important.
I think you should at least keep a decent quality to the vids. You don’t want them too compressed as they’ll just look terrible. As for number of vids, I’m likely the worst person to give advice here (I have girls with 400+ vids), but I like to try to get as many main vids as I can for a girl, which involves watching a lot that she’s done. This takes forever so you might be satisfied with the stuff you can easily get.
If you’re making a mother pack, I would personally advise against tying her to a specific girl. It’s nice to have her free to be used for any girl so players don’t have to use her with a girl they don’t like or don’t have. What is good for a mother pack is a bit different than a daughter pack. I think threesome scenes are more important for moms, office scenes for moms working for you, and public areas as you’re more likely to bang them when out and about. Some vids don’t work on moms (I think gloryhole can never be done by a mom currently, get peed on by the mom can’t be done currently, and I think cumming on food is only a cafeteria action.)
For photoshoot or videoshoots, I recommend around 6 photoshoots as a healthy amount, and maybe 4 videoshoots. Too many photoshoots and the player might feel overwhelmed at the amount you’re throwing at them. Too many videoshoots clogs up the file size of the pack. Remember shared shoots are inherently harder to do, as you need both girls. 
Don’t be too worried by a ton of yellow errors in the girl rating. Some of these are hard to avoid. I don’t think having no events or no matching mom is an issue, for example. 
At the end of the day, it’s all up to you. If you don’t care about file size, then don’t worry about it. If you’re really fighting for storage space, then trim down until you’re happy. 

## Verified Vid Tagger Workflow (2026-10)

### Selecting and splitting clips

In Vid Maker, a proposal is included when its **Include** checkbox is checked or its row is highlighted. If both controls are used, their selections are combined once; a clip present in both is submitted once. Candidates already recorded as completed/tagged/reviewed with an existing output are shown as complete and are not split again. A batch already in progress must finish before another batch can be submitted.

Confirmed boundaries are source-video timestamps stored as integer milliseconds. The split worker converts them to seconds for FFmpeg, validates each staged output, and associates it with the stable candidate ID and original source interval. Splitting and per-clip analysis run outside the GUI thread. Progress is reported for the batch; failures are attached to their candidate, successful outputs are kept when another candidate fails, and cancellation preserves completed outputs. A candidate left in `processing` after an interrupted application run is reconciled against saved clip records; an incomplete candidate becomes a retryable failure rather than being silently treated as complete.

### Model evidence and review

The active YOLO checkpoint has 32 labels. The video path preserves detections at the configured 0.25 confidence threshold, including their frame, box, class, confidence, and model provenance. Action crops are made only from the checkpoint’s `action_event` boxes; each eligible box is classified independently when experimental Action CNN inference is enabled. Other boxes remain contextual evidence and are not sent to the Action CNN. The current Asset CNN is not called by this video-analysis path.

Action CNN results are experimental and unvalidated. A proposed fine-grained action tag remains a review candidate, not a confirmed tag; the user selects a candidate and uses **Apply Tags** to confirm it. YOLO scene-context detections are retained and fused independently from action evidence. The current Vid Tags database has no exact location-tag mapping for those model labels, so they do not automatically add a location tag. The interface’s current location picker uses broad values from the shoot-tag database; the guide’s detailed location vocabulary and those broad values do not map one-to-one. Choose or correct a location manually after reviewing the clip. The YOLO class `location_kitchen` is not present, so kitchen must not be inferred from this checkpoint.

### Main tags, subtags, and filenames

The guide defines main tags as the video action and subtags as context such as clothing, participants, corruption level, or location. The filename convention is a comma-separated main-tag list, then an optional hyphen, then a comma-separated subtag list; for example, `face-cum.webp` uses `face` as the main tag and `cum` as a subtag. The Vid Tags JSON groups selectable values for the UI but does not encode parent IDs or parent-child edges. UI category names are not additional tags or hierarchy nodes. Do not assume that selecting a subtag automatically adds a parent; the current workflow leaves tag selection explicit.

The current Vid Tagger builds the main-tag and subtag filename sections separately and exports the confirmed filename through the existing export workflow. The authoritative `database/vid_tags.json` supplies the main-tag and clothing-based main-tag groups and the clothing, corruption, participant, and third-party subtag values. Location values currently come from `database/shoots_tags.json`, which is a compatibility mismatch with the location list in this guide; no database migration or new tag was made for this audit.

### Newly implemented safeguards

- Highlighted and Include-checked proposals are additive, de-duplicated, and submitted in row order.
- Existing completed clip records are reconciled with proposal sidecars before confirmation, preventing a stale sidecar from resubmitting a completed clip.
- Worker startup failures and FFmpeg launch errors are reported against candidate IDs; retries use a new operation directory and do not overwrite prior outputs.
- Interrupted `processing` records are reconciled on reload and made explicitly retryable while preserving their source interval and candidate identity.
- Scene-context evidence is preserved and fused separately; it produces no automatic location tag when the taxonomy has no exact existing mapping.
- The expandable analysis-evidence pane lists each sampled YOLO detection, its box/ID/confidence, and Action-CNN eligibility/result; unmapped location context is labeled as review-only.

Live visible-GUI acceptance is still required after installing this update. Automated offscreen tests verify selection, worker completion, persistence recovery, and event-loop responsiveness, but do not substitute for interactive acceptance on the user’s desktop.

## Tag vocabulary and clip routing update (2026-10)

The authoritative Vid Tagger location list now includes the detailed guide vocabulary: `bathroom`, `bar`, `beach`, `cafeteria`, `class`, `clinic`, `coffee_shop`, `home`, `locker_room`, `mall`, `office`, `park`, `pier`, `shower`, and `lounge`. These values are in `database/vid_tags.json` under `location_tags`; the matching model/taxonomy inventory records them as source-specific tags. A model observation is still evidence only and does not set a location automatically.

Fullbody assets retain the documented base type in `database/asset_tags/fullbody.json`. The explicit, limited composition allowlist is in `database/asset_tags/fullbody_compositions.json`: `clothed_topless`, `clothed_bottomless`, and `bikini_bottomless`. The Image Workshop lets the reviewer choose one coverage extension for a Fullbody asset. It rejects duplicate or conflicting extensions and does not generate combinations from every base type. Historical `clothed-bottomless` names can be read as the compatibility alias `clothed_bottomless`; existing records are not silently rewritten. Model class labels and indices remain unchanged.

Vid Maker accepts clips through 15.000 seconds, configured at `video.destinations.vid_maker.maximum_seconds` in `config.yaml`. A clip over that limit is incompatible with Vid Maker only; the message offers creating a shorter reviewed segment and states that the original can remain available to other supported workflows. Event and Video Shoot checks remain independent.

Automatically generated action-region proposals are capped at 40 seconds. Longer evidence spans are decomposed into contiguous, non-overlapping children with deterministic boundaries, a shared parent proposal ID, child order/count, retained frame evidence, and an explicit review-boundary warning. The splitter worker rejects an over-limit AI proposal as a final input guard. Manually defined ranges are not treated as automatic proposals.

Confirmed split records retain their source interval and stable candidate identity. Project records can additionally register a user-selected derivative with a stable child ID, parent clip ID, exact source interval, independent tags, and per-workflow eligibility. `Export reviewed feedback` writes only explicit human decisions to versioned JSONL; unresolved suggestions are omitted and no model training occurs.

The existing Vid Maker preview, source timeline, playback controls, and manual boundary fields share the same preview container. Vid Tagger also has a `Select shorter segment for Vid Maker` action for long clips. It opens a dialog with adjustable start and end points, preview controls, and confirm/cancel actions; confirmation extracts a separate derivative and stores its parent ID, exact source interval, and independent routing eligibility. A generated-media integration test verifies extraction and persistence. The current desktop did not expose a Girl Packer window during this implementation session, so visible GUI resizing and playback acceptance remains unverified.

## Final export formats and image specifications

Final pack outputs use WebM for Vid Maker clips, video shoots, and Event Maker video media. Girl Packer encodes VP9 video and Opus audio when the source has audio, then checks the actual container and stream metadata and decodes the result before publishing. The current configurable encoding profile is in `video.exporter` in `config.yaml` (`bitrate` and `crf`). The guide recommends keeping videos at good quality and sourcing clips at 720p or higher; it does not set a mandatory final video resolution, frame rate, bitrate, or codec.

Final pack images use actual WebP encoding. Body images follow the guide's recommended dimensions and aspect ratios: Portrait and T-Portrait 350×350 (1:1), Face 500×500 (1:1), Boobs and Ass 495×240 (about 2.06:1), and Pussy and Legs 245×235 (about 1.04:1). These are guide recommendations rather than an upper-size limit; larger outputs are allowed if the composition retains the listed aspect ratio. Portrait and T-Portrait require transparent backgrounds. Face transparency is optional. Body-part naming continues to use the documented main-tag/subtag structure.

Fullbody images must be transparent, at least 1500 pixels high, and trimmed to the subject's bounds as described above. Processing preserves aspect ratio when increasing a Fullbody image to the minimum height; it does not stretch a subject to fill a fixed canvas. The guide does not specify image dimensions for event media or photoshoot stills, so those outputs preserve their source dimensions.

Image Workshop applies the selected upscaling stage first, background removal second when requested, and WebP encoding last. Alpha-capable source images are loaded without discarding alpha. Temporary PNGs may be used between these stages; final pack validation rejects non-WebP image files. The Image Workshop exposes lossy WebP quality (1–100) and a separate lossless mode. `image.webp_quality` is the configured lossy default; `image.webp_lossless` selects the lossless default. The selected per-asset setting is passed to the final encoder and recorded in the pack manifest. Intermediate upscaler previews and separately saved derivatives may remain PNG or JPEG and are not final pack images.


