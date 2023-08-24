
.PHONY: clean
clean:
	rm -rf build

build/design-system:
	mkdir -p build/design-system
	mkdir -p design_system_tmp
	wget https://github.com/DemocracyClub/design-system/archive/refs/tags/0.3.0.tar.gz \
		-O design_system_tmp/design-system.tar.gz

	cd design_system_tmp && tar -xvzf design-system.tar.gz
	cp -r design_system_tmp/design-system-0.3.0/system/* build/design-system/
	rm -rf design_system_tmp


app/static/public/static/dc-design-system.css: build/design-system app/static/public/static/dc-design-system.scss
	sass -I build/design-system app/static/public/static/dc-design-system.scss:app/static/public/static/dc-design-system.css

app/static/public/static/images: build/design-system
	cp -r build/design-system/images app/static/public/static/images

app/static/public/static/fonts: build/design-system
	cp -r build/design-system/fonts app/static/public/static/fonts

static: app/static/public/static/dc-design-system.css app/static/public/static/images app/static/public/static/fonts


.PHONY: deploy_lambda_at_edge
deploy_lambda_at_edge: static
	cd cdk/functions/node_cognito/ && npm install
	cdk deploy LambdaAtEdgeStack


.PHONY: deploy
deploy: deploy_lambda_at_edge
	cdk deploy ListMonkStack
