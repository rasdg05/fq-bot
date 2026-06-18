import {Config} from '@remotion/cli/config';

// Render seguro en contenedor / CI: JPEG por fotograma y sobrescritura.
Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);

// H.264 + faststart: compatible con el subidor de Meta Ads.
Config.setCodec('h264');
