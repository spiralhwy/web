module.exports = function(eleventyConfig) {
  // Add passthrough copy for posters
  eleventyConfig.addPassthroughCopy({ "src/_data/posters": "posters" });
  eleventyConfig.addPassthroughCopy({ "src/_fonts": "fonts" });
  eleventyConfig.addPassthroughCopy({ "src/css": "css" });

  // Format date as "DayOfWeek DD, Month"
  eleventyConfig.addFilter("formatDate", function(dateString) {
    const date = new Date(dateString.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'));
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      day: 'numeric',
      month: 'long'
    });
  });

  // Format time from "HHMM" to "H:MM AM/PM"
  eleventyConfig.addFilter("formatTime", function(timeString) {
    const hours = parseInt(timeString.substring(0, 2));
    const minutes = timeString.substring(2);
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    return `${displayHours}:${minutes} ${period}`;
  });

  // Sort movies by earliest showing time
  eleventyConfig.addFilter("sortByEarliestShowing", function(movies) {
    return [...movies].sort((a, b) => {
      const aEarliestTime = Math.min(...a.showings.map(s => parseInt(s.time)));
      const bEarliestTime = Math.min(...b.showings.map(s => parseInt(s.time)));
      return aEarliestTime - bEarliestTime;
    });
  });

  // Group movies by date
  eleventyConfig.addFilter("groupBy", function(movies, key) {
    const grouped = {};
    
    // Get all dates from the movies object
    Object.keys(movies).forEach(date => {
      grouped[date] = movies[date];
    });
    
    // Sort dates
    return Object.fromEntries(
      Object.entries(grouped).sort(([dateA], [dateB]) => dateA.localeCompare(dateB))
    );
  });

  return {
    dir: {
      input: "src",
      output: "public",
      includes: "_includes",
    }
  };
};
