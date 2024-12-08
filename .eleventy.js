// .eleventy.js
module.exports = function(eleventyConfig) {

  // copy into public
  eleventyConfig.addPassthroughCopy({ "spiral_hwy/fonts": "fonts" });
  eleventyConfig.addPassthroughCopy({ "spiral_hwy/css/styles.css": "styles.css" });

  // format date string
  // need to replace dashes with slashes for correct evaluation
  eleventyConfig.addFilter("formatDate", function(dateString) {
    const date = new Date(dateString.replace(/-/g, '\/'));
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      day: 'numeric',
      month: 'long'
    });
  });

  // format time
  eleventyConfig.addFilter("formatTime", function(timeString) {
    const hours = parseInt(timeString.substring(0, 2));
    const minutes = timeString.substring(2);
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    return `${displayHours}:${minutes} ${period}`;
  });

  return {
    dir: {
      input: "spiral_hwy",
      output: "public",
    }
  };
};
