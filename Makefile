# iS2ROS Unified Makefile

# Set number of jobs for make
JOBS ?= $(shell nproc)

# Toolchain and path definitions
ARM_TOOLCHAIN = $(CURDIR)/arm_toolchain.cmake
DEPLOY_DIR    = iS2ROS_deploy_arm
DEPLOY_PKG    = iS2ROS_deploy_arm.tar.gz

# x86 Build paths
X86_MAIN_BUILD   = iSSROS/build
X86_ASSESS_BUILD = plugins/assess/build
X86_SELECT_BUILD = plugins/select/build

# ARM Build paths
ARM_MAIN_BUILD   = build_arm_all
ARM_ASSESS_BUILD = build_arm_plugins
ARM_SELECT_BUILD = build_arm_select

.PHONY: all x86 arm clean deploy help

all: x86

help:
	@echo "iS2ROS Build Management:"
	@echo "  make x86     - Build main app and plugins for local x86_64"
	@echo "  make arm     - Cross-compile for ARM aarch64 (requires ./mnt)"
	@echo "  make deploy  - Build ARM and package into $(DEPLOY_PKG)"
	@echo "  make clean   - Remove all build artifacts"

x86:
	@echo ">>> Building x86_64..."
	mkdir -p $(X86_MAIN_BUILD) && cd $(X86_MAIN_BUILD) && cmake .. && make -j$(JOBS)
	mkdir -p $(X86_ASSESS_BUILD) && cd $(X86_ASSESS_BUILD) && cmake .. && make -j$(JOBS)
	mkdir -p $(X86_SELECT_BUILD) && cd $(X86_SELECT_BUILD) && cmake .. && make -j$(JOBS)
	@echo ">>> x86 Build Done."

arm:
	@echo ">>> Cross-compiling for ARM..."
	mkdir -p $(ARM_MAIN_BUILD) && cd $(ARM_MAIN_BUILD) && cmake -DCMAKE_TOOLCHAIN_FILE=$(ARM_TOOLCHAIN) ../iSSROS/cmake/ARM && make -j$(JOBS)
	mkdir -p $(ARM_ASSESS_BUILD) && cd $(ARM_ASSESS_BUILD) && cmake -DCMAKE_TOOLCHAIN_FILE=$(ARM_TOOLCHAIN) ../plugins/assess && make -j$(JOBS)
	mkdir -p $(ARM_SELECT_BUILD) && cd $(ARM_SELECT_BUILD) && cmake -DCMAKE_TOOLCHAIN_FILE=$(ARM_TOOLCHAIN) ../plugins/select && make -j$(JOBS)
	@echo ">>> ARM Build Done."

deploy: arm
	@echo ">>> Creating deployment package..."
	mkdir -p $(DEPLOY_DIR)
	cp $(ARM_MAIN_BUILD)/IROS $(DEPLOY_DIR)/
	cp $(ARM_ASSESS_BUILD)/libAssessPlugin.so $(DEPLOY_DIR)/
	cp $(ARM_SELECT_BUILD)/libselect.so $(DEPLOY_DIR)/
	cp iSSROS/*.py iSSROS/*.txt iSSROS/*.dat $(DEPLOY_DIR)/
	cp -r light_mappo-transformer $(DEPLOY_DIR)/
	cp ./run_iros_yolo.sh ./stop_iros_yolo.sh $(DEPLOY_DIR)/
	cp ./config.ini $(DEPLOY_DIR)/
	cp -r ./Baks $(DEPLOY_DIR)/
	tar -czf $(DEPLOY_PKG) $(DEPLOY_DIR)
	@echo ">>> Deployment package ready: $(DEPLOY_PKG)"

clean:
	rm -rf $(X86_MAIN_BUILD) $(X86_ASSESS_BUILD) $(X86_SELECT_BUILD)
	rm -rf $(ARM_MAIN_BUILD) $(ARM_ASSESS_BUILD) $(ARM_SELECT_BUILD)
	rm -rf $(DEPLOY_DIR) $(DEPLOY_PKG)
	@echo ">>> All cleaned."
