// .eleventy.js
module.exports = function(eleventyConfig) {

  // Existing passthrough copy configurations
  eleventyConfig.addPassthroughCopy({ "src/_data/posters": "posters" });
  eleventyConfig.addPassthroughCopy({ "src/_fonts": "fonts" });
  eleventyConfig.addPassthroughCopy({ "src/css/styles.css": "styles.css" });

  // Existing date formatter
  eleventyConfig.addFilter("formatDate", function(dateString) {
    const date = new Date(dateString.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'));
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      day: 'numeric',
      month: 'long'
    });
  });

  // Existing time formatter
  eleventyConfig.addFilter("formatTime", function(timeString) {
    const hours = parseInt(timeString.substring(0, 2));
    const minutes = timeString.substring(2);
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    return `${displayHours}:${minutes} ${period}`;
  });

  // Modified groupBy filter to handle both date and title grouping
  eleventyConfig.addFilter("groupBy", function(movies, key) {
    if (key === "date") {
      const grouped = {};
      Object.keys(movies).forEach(date => {
        grouped[date] = movies[date];
      });
      return Object.fromEntries(
        Object.entries(grouped).sort(([dateA], [dateB]) => dateA.localeCompare(dateB))
      );
    }
    return movies;
  });

  eleventyConfig.addFilter("groupByTitle", function(movies) {
    const grouped = {};

    movies.forEach(movie => {
        if (!grouped[movie.title]) {
            grouped[movie.title] = {
                title: movie.title,
                rating: movie.rating,
                poster: movie.poster,
                theaters: [],
                earliestTime: Math.min(...movie.showings.map(s => parseInt(s.time)))
            };
        }

        grouped[movie.title].theaters.push({
            name: movie.theater,
            showings: movie.showings,
            map: movie.map,
            area: movie.area,
            theater_link: movie.theater_link
        });
    });

    return Object.values(grouped).sort((a, b) => a.earliestTime - b.earliestTime);
});

  return {
    dir: {
      input: "src",
      output: "public",
    }
  };
};
