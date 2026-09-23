import React from 'react';

/** Public bundle image API: browser-native image attributes, with no private CDN dependency. */
export const Image = React.forwardRef<HTMLImageElement, React.ImgHTMLAttributes<HTMLImageElement>>(
  (props, ref) => <img {...props} ref={ref} />,
);
Image.displayName = 'PreviewImage';
export default Image;
