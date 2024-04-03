# Makefile

# Define variables
SOURCE_MD=email.md
TARGET_HTML=processed.html
TEMPLATE_HTML=../app_assets/templates/default_email.html
FINAL_HTML=final_output.html
INSERTION_POINT={{ template "content" . }}

# Default rule
all: insert_content

# Step 1: Convert Markdown to HTML
$(TARGET_HTML): $(SOURCE_MD)
	pandoc $< -o $@

# Step 2: Insert HTML content into another HTML file
insert_content: $(TARGET_HTML)
	#awk '/$(INSERTION_POINT)/{system("cat $(TARGET_HTML)");next}1' $(TEMPLATE_HTML) | bootstrap-email > $(FINAL_HTML)
	awk '/$(INSERTION_POINT)/{system("cat $(TARGET_HTML)");next}1' $(TEMPLATE_HTML) | bootstrap-email | sed -n '/<!-- StartContent -->/,/<!-- EndContent -->/p' | sed '1d;$d' > $(FINAL_HTML)

# Clean rule to clean up generated files
clean:
	rm -f $(TARGET_HTML) $(FINAL_HTML)
