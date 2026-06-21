import { Config } from "@remotion/cli/config";

// Scenes render as solid-background H.264 clips for the final cut.
Config.setVideoImageFormat("jpeg");
Config.setConcurrency(8);
Config.setOverwriteOutput(true);
