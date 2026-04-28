package com.github.juanfernandez.article.repository;

import com.github.juanfernandez.article.model.Pregunta;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Spring Data JPA repository for {@link Pregunta} entities stored in the
 * {@code preguntas} PostgreSQL table.
 */
public interface PreguntaRepository extends JpaRepository<Pregunta, UUID> {

    /**
     * Returns all questions ordered by their display position.
     *
     * @return questions sorted ascending by {@code orden}
     */
    List<Pregunta> findAllByOrderByOrdenAsc();

    /**
     * Returns the question with the highest {@code orden} value.
     * Used to compute the next available position when inserting a new question.
     *
     * @return the last question by order, or empty if the table is empty
     */
    Optional<Pregunta> findTopByOrderByOrdenDesc();

    /**
     * Returns {@code true} when a question with the given camel-case {@code campo} identifier
     * already exists.
     *
     * @param campo camelCase field name to check
     * @return {@code true} if the campo is already used
     */
    boolean existsByCampo(String campo);

    /**
     * Returns all Spanish question texts ({@code texto->>'es'}) from the table.
     * Used to build the deduplication context sent to the AI provider.
     *
     * @return list of Spanish question strings
     */
    @Query("SELECT p.texto FROM Pregunta p")
    List<java.util.Map<String, String>> findAllTextos();
}
