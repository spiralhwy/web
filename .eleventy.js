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

  // format a theater slug for display (e.g. "alamo_drafthouse_sf" -> "Alamo Drafthouse SF")
  // title-cases each word, but keeps known acronyms fully capitalized
  const UPPERCASE_WORDS = new Set(["sf"]);
  eleventyConfig.addFilter("displayName", function(slug) {
    return String(slug).split("_").map(function(word) {
      const lower = word.toLowerCase();
      return UPPERCASE_WORDS.has(lower)
        ? lower.toUpperCase()
        : lower.charAt(0).toUpperCase() + lower.slice(1);
    }).join(" ");
  });

  return {
    dir: {
      input: "spiral_hwy",
      output: "public",
    }
  };
};
