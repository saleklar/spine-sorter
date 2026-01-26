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
            "title": "Spine Sorter v.5.51",
            "subtitle": "The Animator's Survival Guide",
            "body": [
                "<b>No more manual sorting. No more missing files.</b>",
                "<br/>",
                "This tool ensures your Spine projects are optimal for the game engine.",
                "It thinks like an engineer so you can work like an artist."
            ],
            "is_cover": True
        },
        {
            "title": "What Does This Thing Do?",
            "body": [
                "<b>1. Smart Sorting:</b> Automatically separates JPEGs (opaque) from PNGs (transparent).",
                "<b>2. Safety Checks:</b> Finds files you forgot to export.",
                "<b>3. Broken Link Detector:</b> Finds images that are missing from your computer.",
                "<b>4. Animation Guardian:</b> Counts your animations to make sure none were left behind."
            ]
        },
        {
            "title": "How To Use It (In 4 Steps)",
            "body": [
                "<b>1. Browse:</b> select the folder with your <b>.spine</b> files.",
                "<b>2. Select:</b> Choose the character file from the list.",
                "<b>3. Run:</b> Click the big <b>'Run Selected File'</b> button.",
                "<b>4. Read:</b> Look at the report at the bottom for colored messages."
            ]
        },
        {
            "title": "Understanding the Colors",
            "body": [
                "The log at the bottom uses a simple Traffic Light system:",
                "<br/>",
                "<font color='#32CD32'><b>GREEN messages</b></font> = All good! Relax.",
                "<font color='#FFA500'><b>ORANGE messages</b></font> = <b>Warning.</b> Something might be wrong (check export settings), but it won't crash the game.",
                "<font color='#FF4500'><b>RED messages</b></font> = <b>CRITICAL.</b> Something is definitely broken (missing file, invisible animations)."
            ]
        },
        {
            "title": "The 'Orange' Warnings: Checkboxes",
            "body": [
                "<b>Message:</b> <font color='orange'>'Unchecked for Export'</font>",
                "<br/>",
                "<b>The Problem:</b> You are using an image, attachment, or an entire skeleton that has the <b>Export</b> checkbox UNCHECKED in Spine.",
                "<b>The Result:</b> It looks fine in Spine, but it will be invisible in the game.",
                "<b>The Fix:</b> Go to Spine Tree view, find the item, and check the 'Export' dot."
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
            "title": "Pro Tips for Animators",
            "body": [
                "<b>Additive Blending:</b> Any slot using 'Additive' or 'Screen' blend modes is automatically sent to the JPEG folder (it saves space!).",
                "<b>Reference Images:</b> Keep your ref images in a folder named 'refs' or 'unused'. The tool tries to ignore them.",
                "<b>Final Check:</b> Always scroll to the bottom of the log. If you see <font color='#32CD32'>'Completed OK'</font>, you are safe. If you see <font color='#FFA500'>CHECK THE WARNINGS</font>, scroll up the log."
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
            # Add spacing before new section (unless it's the top of a page, but ReportLab handles flow)
            # We only add spacer if it's not the first item after cover
            if i > 1: 
                story.append(Spacer(1, 25))
                
            story.append(Paragraph(slide["title"], slide_title_style))
            story.append(Spacer(1, 10))
        
            for item in slide["body"]:
                story.append(Paragraph(f"• {item}" if not item[0].isdigit() and not item.startswith("<") else item, bullet_style))
                story.append(Spacer(1, 5))

    doc.build(story)
    print(f"PDF generated: {filename}")

if __name__ == "__main__":
    create_pdf("Spine_Sorter_v5.51_Artist_Guide.pdf")
