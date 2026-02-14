from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

def create_pdf(filename):
    doc = SimpleDocTemplate(filename, pagesize=landscape(letter))
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        alignment=TA_CENTER,
        spaceAfter=30,
        textColor=colors.darkblue
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=50,
        textColor=colors.gray
    )
    
    slide_title_style = ParagraphStyle(
        'SlideTitle',
        parent=styles['Heading2'],
        fontSize=20,
        alignment=TA_LEFT,
        spaceAfter=20,
        textColor=colors.darkblue,
        borderColor=colors.lightgrey,
        borderWidth=0,
        borderPadding=5
    )
    
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=14,
        leading=20,
        identifier='Body'
    )

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontSize=14,
        leading=20,
        leftIndent=20,
        bulletIndent=10
    )

    story = []

    # Content Data
    slides = [
        {
            "title": "Spine Sorter v5.70",
            "subtitle": "The Animator's Survival Guide",
            "body": [
                "<b>No more manual sorting. No more missing files.</b>",
                "<br/>",
                "This tool ensures your Spine projects are optimal for the game engine.",
                "It thinks like an engineer so you can work like an artist.",
                "<br/>",
                "<br/>",
                "<b>WHAT'S NEW IN THIS EDITION (v5.70):</b>",
                "• <b>Beta Version Fix:</b> 'Fetch All' now correctly handles versions with '-beta' suffix (e.g. 4.2.xx-beta).",
                "• <b>Fetch All Versions:</b> New button to grab the complete list of historical Spine patches from the web.",
                "• <b>Mac Support:</b> Fixed Spine version detection for macOS users.",
                "• <b>Active Version Switcher:</b> Dropdown to select and lock the Spine version used for processing.",
                "• <b>Quick Launch:</b> 'LAUNCH SPINE' button to open the specific selected version immediately.",
                "• <b>Smart Open:</b> 'Open after export' now uses the specific version you selected.",
                "• <b>Duplicate-image detection:</b> SHA1-based grouping and RECOMMENDATIONS to dedupe identical attachments.",
                "• <b>Naming-convention checks:</b> Per-skeleton animation/skeleton checks plus summarized slot/bone/constraint examples."
            ],
            "is_cover": True
        },
        {
            "title": "What Does This Thing Do?",
            "body": [
                "<b>1. Smart Sorting:</b> Automatically separates JPEGs (opaque) from PNGs (transparent).",
                "<b>2. Safety Checks:</b> Finds files you forgot to export.",
                "<b>3. Broken Link Detector:</b> Finds images that are missing from your computer.",
                "<b>4. Animation Guardian:</b> Counts your animations to make sure none were left behind.",
                "<b>5. Visibility Police:</b> Finds invisible or hidden slots that shouldn't be there."
            ]
        },
        {
            "title": "How To Use It (In 4 Steps)",
            "body": [
                "<b>1. Browse:</b> Select the folder with your <b>.spine</b> files.",
                "<b>2. Select:</b> Choose the character file from the list.",
                "<b>3. Run:</b> Click the big <b>'Run Selected File'</b> button.",
                "<b>4. Review:</b> A popup report appears with the results. You can save it if you want."
            ]
        },
        {
            "title": "Understanding the Colors",
            "body": [
                "The report uses a simple Traffic Light system:",
                "<br/>",
                "<font color='#32CD32'><b>GREEN messages</b></font> = All good! Relax.",
                "<font color='#87CEFA'><b>BLUE messages</b></font> = <b>Recommendation.</b> Non-critical suggestions to improve naming, reduce disk usage, or follow conventions.",
                "<font color='#FFA500'><b>ORANGE messages</b></font> = <b>Warning.</b> Something might be wrong (check export settings), but it won't crash the game.",
                "<font color='#FF4500'><b>RED messages</b></font> = <b>CRITICAL.</b> Something is definitely broken (missing file, invisible animations)."
            ]
        },
        {
            "title": "Common Warnings: Checkboxes",
            "body": [
                "<b>Message:</b> <font color='orange'>'Unchecked for Export'</font>",
                "<br/>",
                "<b>The Problem:</b> You are using an image, attachment, or an entire skeleton that has the <b>Export</b> checkbox UNCHECKED in Spine.",
                "<b>The Result:</b> It looks fine in Spine, but it will be invisible in the game.",
                "<b>The Fix:</b> Go to Spine Tree view, find the item, and check the 'Export' dot."
            ]
        },
        {
            "title": "New Checks: Hidden & Invisible Items",
            "body": [
                "<b>Message:</b> <font color='orange'>'Slot is HIDDEN in Setup Pose'</font>",
                "<b>Problem:</b> You turned off the visibility dot in Setup Mode. It might never show up in game.",
                "<br/>",
                "<b>Message:</b> <font color='orange'>'Slot is INVISIBLE (Alpha=0)'</font>",
                "<b>Problem:</b> The slot color has 0 alpha in Setup Mode. It is technically there, but invisible.",
                "<br/>",
                "<b>The Fix:</b> Ensure all slots meant to be seen are visible and opaque in the Setup Pose."
            ]
        },
        {
            "title": "New Features: Workflow & Reporting",
            "body": [
                "<b>Validate Only Mode:</b>",
                "Check the box 'Check for Errors Only' to skip image processing. Use this for a super-fast health check of your spine file.",
                "<br/>",
                "<b>Popup Reports:</b>",
                "Reports now open in a clean popup window. You can hit 'Save As' to keep a copy, preventing your folder from filling up with junk text files.",
                "<br/>",
                "<b>Interactive Help:</b>",
                "Hover your mouse over any button or text box to see a tooltip explanation. Click the <b>'?'</b> button to verify this manual."
            ]
        },
        {
            "title": "The 'Red' Errors: Hidden Transparency",
            "body": [
                "<b>Message:</b> <font color='red'>'Forced to PNG (Detected Transparency)'</font>",
                "<br/>",
                "<b>The Problem:</b> You put a file in a JPEG folder (expecting it to be opaque), but we found invisible see-through pixels.",
                "<b>The Result:</b> If we forced it to be a JPEG, it would have ugly white halos in-game.",
                "<b>The Fix:</b> We automatically saved it as a PNG for you. To use JPEG, flattened the alpha channel in Photoshop."
            ]
        },
        {
            "title": "New Protection: The Animation Guard",
            "body": [
                "<b>The Nightmare:</b> You finish a complex animation, but accidentally uncheck 'Export' on the clip itself.",
                "<b>The Reality:</b> Front end developers cannot find your animation.",
                "<br/>",
                "<b>The Solution:</b> This tool compares your Spine project file against the output.",
                "<b>If it sees:</b> <font color='#FF4500'>WARNING:</font> <font color='#FFA500'>1 animations are checked off...</font>",
                "<b>It means:</b> One of your animations is NOT in the game data. Check your export settings!"
            ]
        },
        {
            "title": "New: Version Management",
            "body": [
                "<b>Active Version Dropdown:</b>",
                "Located on the main screen. Allows you to choose exactly which installed Spine version to use (e.g., 4.1.24 vs 4.2.35).",
                "<br/>",
                "<b>LAUNCH SPINE Button:</b>",
                "Instantly opens the Spine Editor with the selected version. Useful for quick fixes.",
                "<br/>",
                "<b>Consistency:</b>",
                "The tool now forces the 'Open after export' features to use the exact version you selected, preventing accidental version upgrades."
            ]
        },
        {
            "title": "Changelog",
             "body": [
                "<b>v5.69:</b>",
                "• <b>New:</b> 'Fetch All' button to retrieve all historical versions from Esoteric Software.",
                "<br/>",
                "<b>v5.68:</b>",
                "• <b>Fix:</b> Resolved Spine version detection issues on macOS.",
                "• <b>Platform:</b> Improved cross-platform compatibility for version launcher.",
                "<br/>",
                "<b>v5.67:</b>",
                "• <b>Feature:</b> Active Version Switcher (Dropdown) & Quick Launcher.",
                "• <b>fix:</b> 'Open after export' now respects the selected version.",
                "• <b>Improvement:</b> Automatic version detection sync between launcher mode and processing.",
                "• <b>UI:</b> Added dedicated version controls and status labels.",
                "• <b>Docs:</b> Updated manual and PDF guide with version management instructions.",
                "<br/>",
                "<b>v5.54:</b> Added duplicate-image recommendations, fuzzy naming checks, skeleton/animation name warnings, validate-only temp-cleanup, and misc fixes.",
                "<b>v5.52:</b> Unchecked Animations detection. Multiple skeletons support.",
                "<b>v5.51:</b> 'Validate Only' mode (Dev). JPEG/PNG edge detection improvements.",
                "<b>v5.0:</b> Smart Image Sorting. Source of Truth verification. JSON Minification."
             ]
        }
        ,
        {
            "title": "All Features By Version",
            "body": [
                "<b>v5.68 (current):</b>",
                "• Mac Support fix for version launcher",
                "<br/>",
                "<b>v5.67:</b>",
                "• Active Spine Version Switcher & Launcher",
                "• Version-aware 'Open after export'",
                "• Duplicate-image deduplication recommendations",
                "• Fuzzy naming checks",
                "<br/>",
                "<b>v5.54:</b>",
                "• Naming-convention checks (skeleton, animations)",
                "• Skeleton & animation name issues shown as WARNINGS",
                "• Validate-only runs clean up temporary JSON/export folders",
                "<br/>",
                "<b>v5.53:</b>",
                "• Hidden/Invisible slot checks in Setup Pose",
                "• Popup report dialog with Save As",
                "• Validate Only moved to main UI",
                "<br/>",
                "<b>v5.52:</b>",
                "• Unchecked Animations detection",
                "• Multiple skeletons support",
                "<br/>",
                "<b>v5.51:</b>",
                "• Initial 'Validate Only' dev option",
                "• Improved JPEG/PNG soft-edge handling",
                "<br/>",
                "<b>v5.0:</b>",
                "• Smart Image Sorting (auto-detect transparency)",
                "• Source-of-truth verification via Spine CLI",
                "• JSON minification option for output files"
            ]
        }
    ]

    for i, slide in enumerate(slides):
        if slide.get("is_cover"):
            story.append(Spacer(1, 100))
            story.append(Paragraph(slide["title"], title_style))
            if "subtitle" in slide:
                story.append(Paragraph(slide["subtitle"], subtitle_style))
            
            for item in slide["body"]:
                story.append(Paragraph(item, body_style)) # Use body style for cover text
                story.append(Spacer(1, 5))
                
            story.append(PageBreak())
        else:
             # Always start a new page for each slide (except the first one which follows cover logic)
             if i > 0 and not slides[i-1].get("is_cover"):
                 story.append(PageBreak())
                
             story.append(Paragraph(slide["title"], slide_title_style))
             story.append(Spacer(1, 10))
        
             for item in slide["body"]:
                 story.append(Paragraph(f"• {item}" if not item[0].isdigit() and not item.startswith("<") else item, bullet_style))
                 story.append(Spacer(1, 5))

    doc.build(story)
    print(f"PDF generated: {filename}")

if __name__ == "__main__":
    create_pdf("Spine_Sorter_v5.70_Artist_Guide.pdf")
