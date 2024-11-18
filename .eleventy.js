module.exports = function(eleventyConfig) {
  // Add passthrough copy for posters
  eleventyConfig.addPassthroughCopy({ "src/_data/posters": "posters" });

  // Get all unique dates
  eleventyConfig.addFilter("getAllDates", function(theaters) {
    if (!theaters) return [];
    
    const dates = new Set();
    Object.entries(theaters).forEach(([theater, movies]) => {
      if (Array.isArray(movies)) {
        movies.forEach(movie => {
          if (movie && movie.date) {
            dates.add(movie.date);
          }
        });
      }
    });
    return Array.from(dates).sort();
  });

  // Get all movies for a specific date, grouped by movie title
  eleventyConfig.addFilter("getMoviesByTitle", function(theaters, date) {
    if (!theaters || !date) return {};
    
    const moviesByTitle = {};
    
    Object.entries(theaters).forEach(([theater, movies]) => {
      if (Array.isArray(movies)) {
        movies.forEach(movie => {
          if (movie && movie.date === date) {
            if (!moviesByTitle[movie.title]) {
              moviesByTitle[movie.title] = {
                title: movie.title,
                rating: movie.rating,
                poster: movie.poster,
                theaters: {}
              };
            }
            moviesByTitle[movie.title].theaters[theater] = movie.showings;
          }
        });
      }
    });
    
    return moviesByTitle;
  });

  return {
    dir: {
      input: "src",
      output: "public",
      includes: "_includes",
      // data: "_data"
    }
  };
};
