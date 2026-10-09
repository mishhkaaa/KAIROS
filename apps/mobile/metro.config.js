// @kairos/contracts is a file: dependency outside this project (shared/ts), so Metro must watch it.
const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);
config.watchFolders = [...(config.watchFolders ?? []), path.resolve(__dirname, "../../shared/ts")];

module.exports = config;
