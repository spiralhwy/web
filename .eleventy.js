// .eleventy.js
module.exports = function(eleventyConfig) {

  // keep saved test fixtures (copies of theater websites) out of the published site
  eleventyConfig.ignores.add("spiral_hwy/tests/**");

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

  // site-wide values used for SEO metadata, robots.txt, and sitemap.xml
  eleventyConfig.addGlobalData("site", {
    url: "https://www.spiralhwy.com",
    buildDate: new Date().toISOString().slice(0, 10),
  });

  // collect the unique theaters across all listings, sorted by slug
  eleventyConfig.addFilter("uniqueTheaters", function(movies) {
    const theaters = new Map();
    (movies || []).forEach(function(day) {
      day.movies.forEach(function(movie) {
        movie.listings.forEach(function(listing) {
          if (!theaters.has(listing.theater)) {
            theaters.set(listing.theater, listing);
          }
        });
      });
    });
    return Array.from(theaters.values()).sort(function(a, b) {
      return a.theater.localeCompare(b.theater);
    });
  });

  return {
    dir: {
      input: "spiral_hwy",
      output: "public",
    }
  };
};
